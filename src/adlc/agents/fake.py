"""Scripted models for tests and local runs (006 research R-13). No network, no keys needed.

``FakeGateway`` is the real ``RoutingGateway`` over a ``FakeTransport``, so tests exercise the
gateway's rules and records exactly as production does.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from adlc.agents.catalogue import ModelCatalogue, ModelEntry, estimate_tokens
from adlc.agents.gateway import (
    CallRecorder,
    NullRecorder,
    Outcome,
    ProviderReply,
    RoutingGateway,
    request_tokens,
)
from adlc.orchestration.interfaces import Clock, SystemClock

Script = (
    ProviderReply | Sequence[ProviderReply] | Callable[[Sequence[Mapping[str, str]]], ProviderReply]
)


def reply(
    text: str = "{}",
    *,
    outcome: str = "ok",
    tokens: tuple[int, int] | None | str = "auto",
    reason: str | None = None,
) -> ProviderReply:
    """A scripted reply. ``tokens=None`` means the provider sent no usage figures; by default an
    outage reports no tokens and any other reply 10 in and 5 out."""
    if tokens == "auto":
        tokens = (0, 0) if outcome == Outcome.OUTAGE.value else (10, 5)
    if tokens is None or isinstance(tokens, str):
        return ProviderReply(Outcome(outcome), text, 0, 0, True, reason)
    return ProviderReply(Outcome(outcome), text, tokens[0], tokens[1], False, reason)


@dataclass
class FakeTransport:
    script: Mapping[str, Script] = field(default_factory=dict)
    default: ProviderReply = field(default_factory=reply)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _used: dict[str, int] = field(default_factory=dict)

    def call(
        self,
        entry: ModelEntry,
        messages: Sequence[Mapping[str, str]],
        max_tokens: int,
        timeout_s: float,
        api_key: str,
    ) -> ProviderReply:
        self.calls.append(
            {
                "model": entry.model,
                "messages": [dict(m) for m in messages],
                "max_tokens": max_tokens,
                "timeout_s": timeout_s,
                "api_key": api_key,
            }
        )
        planned = self.script.get(entry.model, self.default)
        if callable(planned):
            result = planned(messages)
        elif isinstance(planned, ProviderReply):
            result = planned
        else:
            n = self._used.get(entry.model, 0)
            self._used[entry.model] = n + 1
            result = planned[min(n, len(planned) - 1)]
        if result.usage_estimated:  # mimic the real transport's estimate
            return ProviderReply(
                result.outcome,
                result.text,
                request_tokens(messages),
                estimate_tokens(result.text),
                True,
                result.reason,
            )
        return result


@dataclass
class MemoryRecorder:
    rows: list[Mapping[str, Any]] = field(default_factory=list)

    def record(self, row: Mapping[str, Any]) -> None:
        self.rows.append(dict(row))


class FakeGateway(RoutingGateway):
    """The production gateway rules over scripted replies; every provider keyed by default."""

    def __init__(
        self,
        catalogue: ModelCatalogue,
        script: Mapping[str, Script] | None = None,
        *,
        keys: Mapping[str, str | None] | None = None,
        recorder: CallRecorder | None = None,
        clock: Clock | None = None,
        default: ProviderReply | None = None,
    ) -> None:
        providers = {e.provider for entries in catalogue.tiers.values() for e in entries}
        super().__init__(
            catalogue=catalogue,
            keys=dict(keys) if keys is not None else {p: f"fake-{p}" for p in providers},
            transport=FakeTransport(dict(script or {}), default or reply()),
            recorder=recorder or NullRecorder(),
            clock=clock or SystemClock(),
        )

    @property
    def fake(self) -> FakeTransport:
        if not isinstance(self.transport, FakeTransport):
            raise TypeError("FakeGateway always has a FakeTransport")
        return self.transport
