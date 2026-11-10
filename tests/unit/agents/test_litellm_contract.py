"""T015: LiteLLM 1.106.5 request bodies and reply mapping over mocked HTTP (R-01, R-02, R-17).

No network: respx intercepts LiteLLM's HTTP for the three providers.
"""

import json
import os
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adlc.agents.catalogue import ModelEntry
from adlc.agents.gateway import LiteLLMTransport, Outcome

pytestmark = pytest.mark.litellm_contract

ANTHROPIC = "https://api.anthropic.com/v1/messages"
OPENAI = "https://api.openai.com/v1/chat/completions"
GEMINI_HOST = "generativelanguage.googleapis.com"
NEVER_SENT = {
    "temperature",
    "top_p",
    "top_k",
    "thinking",
    "reasoning_effort",
    "response_format",
    "tool_choice",
}
MESSAGES = [{"role": "system", "content": "rules"}, {"role": "user", "content": "review this"}]


def _entry(model: str) -> ModelEntry:
    return ModelEntry(model.split("/")[0], model, Decimal(1), Decimal(1), 100, 1000, "internal")


def _anthropic(
    stop: str = "end_turn", text: str = '{"ok": true}', usage: bool = True
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop,
        "stop_sequence": None,
    }
    if usage:
        body["usage"] = {"input_tokens": 11, "output_tokens": 7}
    return body


@pytest.fixture
def http() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def _call(model: str, key: str = "test-key") -> Any:
    return LiteLLMTransport().call(_entry(model), MESSAGES, 64, 5.0, key)


def test_anthropic_body_and_success(http: respx.MockRouter) -> None:
    route = http.post(ANTHROPIC).mock(return_value=httpx.Response(200, json=_anthropic()))
    result = _call("anthropic/claude-opus-5-5", key="anthropic-test-key")
    assert (result.outcome, result.text, result.tokens_in, result.tokens_out) == (
        Outcome.OK,
        '{"ok": true}',
        11,
        7,
    )
    request = route.calls.last.request
    body = json.loads(request.content)
    assert not NEVER_SENT & set(body), body
    assert body["max_tokens"] == 64 and body["system"]
    assert request.headers["x-api-key"] == "anthropic-test-key"
    assert not any(v == "anthropic-test-key" for v in os.environ.values())


@pytest.mark.parametrize(
    ("stop", "text", "outcome"),
    [
        ("refusal", "I can't", Outcome.REFUSAL),
        ("max_tokens", "{", Outcome.TRUNCATED),
        ("end_turn", "", Outcome.TRUNCATED),
    ],
)
def test_anthropic_refusal_and_truncation(
    http: respx.MockRouter, stop: str, text: str, outcome: Outcome
) -> None:
    http.post(ANTHROPIC).mock(return_value=httpx.Response(200, json=_anthropic(stop, text)))
    assert _call("anthropic/claude-opus-5-5").outcome == outcome


def test_anthropic_reply_without_usage_is_not_an_outage(http: respx.MockRouter) -> None:
    """R-17: LiteLLM raises a connection error for a malformed reply; never a fallback."""
    http.post(ANTHROPIC).mock(return_value=httpx.Response(200, json=_anthropic(usage=False)))
    result = _call("anthropic/claude-opus-5-5")
    assert (result.outcome, result.reason) == (Outcome.REQUEST_ERROR, "malformed_reply")


@pytest.mark.parametrize(
    ("response", "outcome", "reason"),
    [
        (
            httpx.Response(
                429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "x"}}
            ),
            Outcome.OUTAGE,
            "rate_limit",
        ),
        (
            httpx.Response(
                400,
                json={"type": "error", "error": {"type": "invalid_request_error", "message": "x"}},
            ),
            Outcome.REQUEST_ERROR,
            "bad_request",
        ),
        (
            httpx.Response(
                401,
                json={"type": "error", "error": {"type": "authentication_error", "message": "x"}},
            ),
            Outcome.OUTAGE,
            "auth",
        ),
        (
            httpx.Response(
                529, json={"type": "error", "error": {"type": "overloaded_error", "message": "x"}}
            ),
            Outcome.OUTAGE,
            "server",
        ),
    ],
)
def test_anthropic_errors(
    http: respx.MockRouter, response: httpx.Response, outcome: Outcome, reason: str
) -> None:
    http.post(ANTHROPIC).mock(return_value=response)
    result = _call("anthropic/claude-opus-5-5")
    assert (result.outcome, result.reason) == (outcome, reason)


def test_timeout_and_connection_failure_are_outages(http: respx.MockRouter) -> None:
    http.post(ANTHROPIC).mock(side_effect=httpx.ReadTimeout("slow"))
    assert _call("anthropic/claude-opus-5-5").outcome == Outcome.OUTAGE
    http.post(ANTHROPIC).mock(side_effect=httpx.ConnectError("down"))
    result = _call("anthropic/claude-opus-5-5")
    assert result.outcome == Outcome.OUTAGE


@pytest.mark.parametrize(
    ("finish", "text", "outcome"),
    [
        ("stop", "ok", Outcome.OK),
        ("content_filter", "", Outcome.REFUSAL),
        ("length", "x", Outcome.TRUNCATED),
    ],
)
def test_openai(http: respx.MockRouter, finish: str, text: str, outcome: Outcome) -> None:
    route = http.post(OPENAI).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": finish,
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
        )
    )
    result = _call("openai/gpt-4o-mini", key="openai-test-key")
    assert result.outcome == outcome
    body = json.loads(route.calls.last.request.content)
    assert not NEVER_SENT & set(body) and body["max_tokens"] == 64
    assert route.calls.last.request.headers["authorization"] == "Bearer openai-test-key"


@pytest.mark.parametrize(
    ("finish", "text", "outcome"),
    [
        ("STOP", "ok", Outcome.OK),
        ("SAFETY", "", Outcome.REFUSAL),
        ("MAX_TOKENS", "x", Outcome.TRUNCATED),
    ],
)
def test_gemini(http: respx.MockRouter, finish: str, text: str, outcome: Outcome) -> None:
    route = http.route(host=GEMINI_HOST).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": text}], "role": "model"},
                        "finishReason": finish,
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 4,
                    "candidatesTokenCount": 2,
                    "totalTokenCount": 6,
                },
            },
        )
    )
    result = _call("gemini/gemini-2.5-flash", key="gemini-test-key")
    assert result.outcome == outcome
    request = route.calls.last.request
    assert "gemini-test-key" not in str(request.url)
    body = json.loads(request.content)
    assert not NEVER_SENT & set(body) and not NEVER_SENT & set(body.get("generationConfig", {}))
