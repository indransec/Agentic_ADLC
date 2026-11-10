"""The model gateway: the only way agents and the reviewer reach a model (006 contracts/gateway.md).

``RoutingGateway`` owns the rules:

- walk the selected profile's entries for the tier in order;
- skip an entry with no key, one not approved for the run's data class, or one whose context
  window is too small;
- move to the next entry only on an outage;
- return a refusal, a truncated answer or a request error at once, never trying another model;
- record every request (``run.model_call``) and trace it without content.

A ``Transport`` performs one request: ``LiteLLMTransport`` in production (research R-01, R-02,
R-17), ``FakeTransport`` in tests.
"""

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from adlc.agents.catalogue import ModelCatalogue, ModelEntry, estimate_tokens
from adlc.agents.telemetry import set_attributes
from adlc.orchestration.interfaces import Clock, SystemClock
from adlc.orchestration.tracing import span

UNAVAILABLE = "unavailable"
AVAILABILITY_REASONS = frozenset({"no_key", "auth"})


class Outcome(StrEnum):
    OK = "ok"
    OUTAGE = "outage"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    REQUEST_ERROR = "request_error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CallIds:
    run_id: str
    usecase_id: str
    terminal_id: str
    agent_id: str
    attempt_ref: str  # run_id/kind/attempt


@dataclass(frozen=True)
class ModelRequest:
    tier: str
    data_class: str  # the run's ceiling
    messages: tuple[Mapping[str, str], ...]
    max_tokens: int
    timeout_s: float
    ids: CallIds
    prompt_hash: str | None
    context_hash: str


@dataclass(frozen=True)
class ProviderReply:
    outcome: Outcome
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    usage_estimated: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    outcome: str  # ok | refusal | truncated | request_error | unavailable
    text: str = ""
    provider: str | None = None
    model: str | None = None
    fallback: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal | None = Decimal(0)
    tried: tuple[Mapping[str, Any], ...] = ()
    reason: str | None = None


class Transport(Protocol):
    def call(
        self,
        entry: ModelEntry,
        messages: Sequence[Mapping[str, str]],
        max_tokens: int,
        timeout_s: float,
        api_key: str,
    ) -> ProviderReply: ...


class CallRecorder(Protocol):
    def record(self, row: Mapping[str, Any]) -> None: ...


class NullRecorder:
    def record(self, row: Mapping[str, Any]) -> None:
        return None


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


def request_tokens(messages: Sequence[Mapping[str, str]]) -> int:
    return estimate_tokens("".join(m.get("content", "") for m in messages))


@dataclass
class RoutingGateway:
    catalogue: ModelCatalogue
    keys: Mapping[str, str | None]
    transport: Transport
    recorder: CallRecorder = field(default_factory=NullRecorder)
    clock: Clock = field(default_factory=SystemClock)
    after_record: Callable[[Mapping[str, Any]], None] | None = None  # e.g. cost alerts

    def complete(self, request: ModelRequest) -> ModelResponse:
        tried: list[dict[str, Any]] = []
        first_runnable: int | None = None
        size = request_tokens(request.messages)
        for index, entry in enumerate(self.catalogue.entries(request.tier), start=1):
            key = self.keys.get(entry.provider)
            skip = (
                "no_key"
                if not key
                else "data_class"
                if not self.catalogue.allows(entry, request.data_class)
                else "context"
                if not entry.fits(size)
                else None
            )
            if skip is not None or key is None:
                reason = skip or "no_key"
                self._record(
                    request,
                    entry,
                    index,
                    ProviderReply(Outcome.SKIPPED, reason=reason),
                    0.0,
                    False,
                    tried,
                )
                tried.append(
                    {"model": entry.model, "outcome": Outcome.SKIPPED.value, "reason": reason}
                )
                continue
            if first_runnable is None:
                first_runnable = index
            fallback = index != first_runnable
            started = time.perf_counter()
            with span("model", "call", **_span_ids(request)) as s:
                reply = self.transport.call(
                    entry,
                    request.messages,
                    entry.capped(request.max_tokens),
                    request.timeout_s,
                    key,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                cost = _cost(entry, reply)
                set_attributes(
                    s,
                    {
                        "agent_id": request.ids.agent_id,
                        "tier": request.tier,
                        "provider": entry.provider,
                        "model": entry.model,
                        "entry_index": index,
                        "tokens_in": reply.tokens_in,
                        "tokens_out": reply.tokens_out,
                        "cost_usd": None if cost is None else float(cost),
                        "cost_known": cost is not None,
                        "outcome": reply.outcome.value,
                        "reason": reply.reason,
                        "fallback": fallback,
                        "latency_ms": round(latency_ms, 1),
                    },
                )
            self._record(request, entry, index, reply, latency_ms, fallback, tried)
            if reply.outcome == Outcome.OUTAGE:
                tried.append(
                    {"model": entry.model, "outcome": reply.outcome.value, "reason": reply.reason}
                )
                continue
            return ModelResponse(
                outcome=reply.outcome.value,
                text=reply.text if reply.outcome == Outcome.OK else "",
                provider=entry.provider,
                model=entry.model,
                fallback=fallback,
                tokens_in=reply.tokens_in,
                tokens_out=reply.tokens_out,
                cost_usd=cost,
                tried=tuple(tried),
                reason=reply.reason,
            )
        waiting_helps = not tried or any(
            t["outcome"] == Outcome.OUTAGE.value or t["reason"] in AVAILABILITY_REASONS
            for t in tried
        )
        return ModelResponse(
            outcome=UNAVAILABLE if waiting_helps else Outcome.REQUEST_ERROR.value,
            tried=tuple(tried),
            reason="no model of the tier could run"
            if waiting_helps
            else "no model of the tier is approved for this data class or context size",
        )

    def _record(
        self,
        request: ModelRequest,
        entry: ModelEntry,
        index: int,
        reply: ProviderReply,
        latency_ms: float,
        fallback: bool,
        tried: list[dict[str, Any]],
    ) -> None:
        cost = _cost(entry, reply)
        row = {
            "agent_attempt_ref": request.ids.attempt_ref,
            "run_id": request.ids.run_id,
            "usecase_id": request.ids.usecase_id,
            "terminal_id": request.ids.terminal_id,
            "agent_id": request.ids.agent_id,
            "tier": request.tier,
            "entry_index": index,
            "provider": entry.provider,
            "model": entry.model,
            "prompt_hash": request.prompt_hash,
            "context_hash": request.context_hash,
            "tokens_in": reply.tokens_in,
            "tokens_out": reply.tokens_out,
            "usage_estimated": reply.usage_estimated,
            "cost_usd": cost,
            "cost_known": cost is not None,
            "latency_ms": round(latency_ms, 3),
            "outcome": reply.outcome.value,
            "reason": None if reply.reason is None else reply.reason[:200],
            "fallback": fallback and reply.outcome == Outcome.OK,
            "tried": list(tried),
            "called_at": self.clock.now(),
        }
        self.recorder.record(row)
        if self.after_record is not None:
            self.after_record(row)


def _cost(entry: ModelEntry, reply: ProviderReply) -> Decimal | None:
    """A call without reported usage costs nothing; otherwise priced (None when unknown)."""
    if reply.tokens_in == 0 and reply.tokens_out == 0:
        return Decimal(0)
    return entry.cost(reply.tokens_in, reply.tokens_out)


def _span_ids(request: ModelRequest) -> dict[str, str]:
    return {
        "run_id": request.ids.run_id,
        "usecase_id": request.ids.usecase_id,
        "terminal_id": request.ids.terminal_id,
    }


# ---------------------------------------------------------------------------- LiteLLM


def _litellm() -> Any:
    """Import LiteLLM lazily (it takes seconds) with no network at import and no telemetry."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm  # noqa: PLC0415 - deliberate lazy import

    litellm.telemetry = False
    litellm.suppress_debug_info = True
    litellm.success_callback = []
    litellm.failure_callback = []
    litellm.callbacks = []
    return litellm


REFUSAL_FINISH = frozenset({"content_filter", "refusal"})


class LiteLLMTransport:
    """One request through LiteLLM, classified per research R-02 and R-17."""

    def call(
        self,
        entry: ModelEntry,
        messages: Sequence[Mapping[str, str]],
        max_tokens: int,
        timeout_s: float,
        api_key: str,
    ) -> ProviderReply:
        litellm = _litellm()
        exc_mod = litellm.exceptions
        try:
            response = litellm.completion(
                model=entry.model,
                messages=[dict(m) for m in messages],
                max_tokens=max_tokens,
                timeout=timeout_s,
                api_key=api_key,
                num_retries=0,
                **dict(entry.params),
            )
        except exc_mod.ContentPolicyViolationError:
            return ProviderReply(Outcome.REFUSAL, reason="content_policy")
        except exc_mod.ContextWindowExceededError:
            return ProviderReply(Outcome.REQUEST_ERROR, reason="context_window")
        except exc_mod.RateLimitError:
            return ProviderReply(Outcome.OUTAGE, reason="rate_limit")
        except exc_mod.Timeout:
            return ProviderReply(Outcome.OUTAGE, reason="timeout")
        except (exc_mod.AuthenticationError, exc_mod.PermissionDeniedError):
            return ProviderReply(Outcome.OUTAGE, reason="auth")
        except (
            exc_mod.ServiceUnavailableError,
            exc_mod.InternalServerError,
            exc_mod.BadGatewayError,
        ):
            return ProviderReply(Outcome.OUTAGE, reason="server")
        except (
            exc_mod.BadRequestError,
            exc_mod.NotFoundError,
            exc_mod.UnprocessableEntityError,
        ):
            return ProviderReply(Outcome.REQUEST_ERROR, reason="bad_request")
        except exc_mod.APIConnectionError as exc:
            # R-17: LiteLLM wraps a malformed reply (e.g. missing usage) as a connection error;
            # only a real transport failure is an outage.
            if _malformed(exc):
                return ProviderReply(Outcome.REQUEST_ERROR, reason="malformed_reply")
            return ProviderReply(Outcome.OUTAGE, reason="connection")
        except exc_mod.APIError as exc:
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and status >= 500:
                return ProviderReply(Outcome.OUTAGE, reason="server")
            return ProviderReply(Outcome.REQUEST_ERROR, reason="api_error")
        return _classify(response, messages)


MALFORMED = (KeyError, TypeError, ValueError, AttributeError, IndexError)


def _malformed(exc: BaseException) -> bool:
    """True when the error chain holds a parsing failure rather than a network failure."""
    seen: set[int] = set()
    current: BaseException | None = exc.__cause__ or exc.__context__
    while current is not None and id(current) not in seen:
        if isinstance(current, MALFORMED):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _classify(response: Any, messages: Sequence[Mapping[str, str]]) -> ProviderReply:
    choice = response.choices[0]
    finish = str(choice.finish_reason or "")
    text = str(choice.message.content or "")
    usage = getattr(response, "usage", None)
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
    estimated = usage is None or (tokens_in == 0 and tokens_out == 0)
    if estimated:
        tokens_in, tokens_out = request_tokens(messages), estimate_tokens(text)
    if finish in REFUSAL_FINISH:
        outcome, reason = Outcome.REFUSAL, finish
    elif finish == "length" or not text.strip():
        outcome, reason = Outcome.TRUNCATED, finish or "empty"
    else:
        outcome, reason = Outcome.OK, None
    return ProviderReply(outcome, text, tokens_in, tokens_out, estimated, reason)
