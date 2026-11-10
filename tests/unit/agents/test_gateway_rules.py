"""T014: gateway rules over a scripted transport (contracts/gateway.md, FR-004 to FR-007)."""

from decimal import Decimal
from typing import Any

import pytest

from adlc.agents.catalogue import ModelCatalogue
from adlc.agents.fake import FakeGateway, MemoryRecorder, reply
from adlc.agents.gateway import CallIds, ModelRequest, Outcome

RANK = {"public": 1, "internal": 2, "confidential_masked": 4, "confidential": 5}


def _entry(
    provider: str,
    model: str,
    *,
    price: float | None = 1.0,
    ctx: int = 1000,
    data: str = "confidential_masked",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "input_per_mtok": price,
        "output_per_mtok": price,
        "max_output_tokens": 50,
        "context_tokens": ctx,
        "max_data_class": data,
    }


def _catalogue(*entries: dict[str, Any]) -> ModelCatalogue:
    return ModelCatalogue.from_content(
        {"profiles": {"default": {"reasoning": list(entries)}}}, "default", RANK
    )


THREE = _catalogue(_entry("anthropic", "a/1"), _entry("openai", "o/1"), _entry("gemini", "g/1"))
KEYS = {"anthropic": "ka", "openai": "ko", "gemini": "kg"}


def _request(text: str = "hello", data_class: str = "internal") -> ModelRequest:
    return ModelRequest(
        tier="reasoning",
        data_class=data_class,
        messages=({"role": "system", "content": "s"}, {"role": "user", "content": text}),
        max_tokens=500,
        timeout_s=30.0,
        ids=CallIds("UC-0001/T1/run-1", "UC-0001", "T1", "agent-x", "UC-0001/T1/run-1/build/1"),
        prompt_hash=None,
        context_hash="sha256:" + "c" * 64,
    )


def _gateway(
    script: dict[str, Any], keys: dict[str, str] = KEYS, catalogue: ModelCatalogue = THREE
) -> tuple[FakeGateway, MemoryRecorder]:
    recorder = MemoryRecorder()
    return FakeGateway(catalogue, script, keys=keys, recorder=recorder), recorder


def test_primary_answers_without_fallback() -> None:
    gateway, recorder = _gateway({"a/1": reply("ok", tokens=(100, 20))})
    response = gateway.complete(_request())
    assert (response.outcome, response.model, response.fallback) == ("ok", "a/1", False)
    assert response.text == "ok" and response.tried == ()
    assert [r["outcome"] for r in recorder.rows] == ["ok"]
    assert recorder.rows[0]["cost_usd"] == Decimal("0.000120") and recorder.rows[0]["cost_known"]
    assert gateway.fake.calls[0]["max_tokens"] == 50  # capped at the entry's output limit
    assert gateway.fake.calls[0]["api_key"] == "ka"


@pytest.mark.parametrize("reason", ["rate_limit", "timeout", "connection", "server", "auth"])
def test_outages_move_to_the_next_entry(reason: str) -> None:
    gateway, recorder = _gateway(
        {"a/1": reply("", outcome="outage", reason=reason), "o/1": reply("fine")}
    )
    response = gateway.complete(_request())
    assert (response.outcome, response.model, response.fallback) == ("ok", "o/1", True)
    assert response.tried == ({"model": "a/1", "outcome": "outage", "reason": reason},)
    assert [r["outcome"] for r in recorder.rows] == ["outage", "ok"]
    assert recorder.rows[1]["tried"] == [{"model": "a/1", "outcome": "outage", "reason": reason}]
    assert recorder.rows[0]["cost_usd"] == Decimal("0") and recorder.rows[0]["fallback"] is False


@pytest.mark.parametrize("outcome", [Outcome.REFUSAL, Outcome.TRUNCATED, Outcome.REQUEST_ERROR])
def test_refusal_truncation_and_request_errors_never_fall_back(outcome: Outcome) -> None:
    gateway, recorder = _gateway({"a/1": reply("", outcome=outcome.value, tokens=(10, 1))})
    response = gateway.complete(_request())
    assert (response.outcome, response.model, response.fallback) == (outcome.value, "a/1", False)
    assert [c["model"] for c in gateway.fake.calls] == ["a/1"]
    assert [r["outcome"] for r in recorder.rows] == [outcome.value]
    assert recorder.rows[0]["cost_usd"] == Decimal("0.000011")  # usage reported, so costed


def test_skips_for_key_data_class_and_context() -> None:
    catalogue = _catalogue(
        _entry("anthropic", "a/1"),  # no key below
        _entry("openai", "o/small", data="internal"),  # below the ceiling
        _entry("openai", "o/tiny", ctx=5),  # context too small
        _entry("gemini", "g/1"),
    )
    gateway, recorder = _gateway(
        {"g/1": reply("ok")}, keys={"openai": "ko", "gemini": "kg"}, catalogue=catalogue
    )
    response = gateway.complete(_request("x" * 100, data_class="confidential_masked"))
    assert (response.outcome, response.model, response.fallback) == ("ok", "g/1", False)
    assert [(r["model"], r["outcome"], r["reason"]) for r in recorder.rows] == [
        ("a/1", "skipped", "no_key"),
        ("o/small", "skipped", "data_class"),
        ("o/tiny", "skipped", "context"),
        ("g/1", "ok", None),
    ]
    assert [c["model"] for c in gateway.fake.calls] == ["g/1"]


def test_full_outage_is_unavailable() -> None:
    gateway, _ = _gateway(
        {m: reply("", outcome="outage", reason="server") for m in ("a/1", "o/1", "g/1")}
    )
    assert gateway.complete(_request()).outcome == "unavailable"
    nokeys, _ = _gateway({}, keys={})
    assert nokeys.complete(_request()).outcome == "unavailable"


def test_all_skipped_for_data_class_cannot_succeed_by_waiting() -> None:
    gateway, recorder = _gateway({})
    response = gateway.complete(_request(data_class="confidential"))  # above every approval
    assert response.outcome == "request_error"
    assert {r["reason"] for r in recorder.rows} == {"data_class"}
    resolver = gateway.complete(_request(data_class="per_T2_prod_design"))
    assert resolver.outcome == "request_error"  # an unresolved ceiling fails closed


def test_unknown_price_and_estimated_usage() -> None:
    catalogue = _catalogue(_entry("openai", "o/free", price=None))
    gateway, recorder = _gateway(
        {"o/free": reply("abcd" * 10, tokens=None)}, keys={"openai": "ko"}, catalogue=catalogue
    )
    response = gateway.complete(_request("abcd" * 25))
    row = recorder.rows[0]
    assert row["cost_usd"] is None and row["cost_known"] is False and response.cost_usd is None
    assert row["usage_estimated"] is True and row["tokens_out"] == 10 and row["tokens_in"] > 0


def test_one_record_per_request_with_ids() -> None:
    gateway, recorder = _gateway({"a/1": reply("", outcome="outage", reason="timeout")})
    gateway.complete(_request())
    assert len(recorder.rows) == len(gateway.fake.calls) == 2  # a/1 outage, then o/1 answers
    row = recorder.rows[0]
    assert (row["run_id"], row["terminal_id"], row["agent_id"], row["tier"]) == (
        "UC-0001/T1/run-1",
        "T1",
        "agent-x",
        "reasoning",
    )
    assert row["entry_index"] == 1 and row["provider"] == "anthropic"
