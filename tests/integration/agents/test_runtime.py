"""T023: model agents in the orchestrator, with scripted models (US2; FR-006, FR-010, FR-013,
FR-014; SC-003 to SC-005)."""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

import pytest

from adlc.agents.fake import reply
from adlc.agents.gateway import ProviderReply
from adlc.agents.store import attempts, model_calls
from adlc.config.settings import DEFAULT_AGENT_LIMITS, AgentLimit
from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.lifecycle import walk_to
from tests.support.orchestration import SYNTHETIC

from .support import BAD, GOOD, MODELS, PRIMARY, T1_AGENT


def test_model_build_records_the_attempt(model_harness: Any) -> None:
    h, late = model_harness({PRIMARY: reply(GOOD, tokens=(1200, 300))})
    usecase, t1 = walk_to(h, "T1")
    run = h.run(t1)
    assert run.state == "awaiting_sign_off", run
    rows = attempts(h.app, t1)
    build = [r for r in rows if r["kind"] == "build"]
    assert len(build) == 1
    a = build[0]
    assert (a["agent_id"], a["implementation"], a["outcome"], a["steps"]) == (
        T1_AGENT,
        "model",
        "artifacts",
        1,
    )
    assert a["context_hash"].startswith("sha256:") and a["prompt_hash"].startswith("sha256:")
    assert set(a["playbook_hashes"]) == {"PB-T1-01", "PB-T1-02", "PB-T1-03"}
    assert (a["tokens_in"], a["tokens_out"]) == (1200, 300)
    calls = model_calls(h.app, t1)
    assert [(c["model"], c["outcome"]) for c in calls] == [(PRIMARY, "ok")]
    assert calls[0]["context_hash"] == a["context_hash"]
    # The model received the spec and the T0 evidence as data blocks, never in the system prompt.
    sent = late.gateway.fake.calls[0]["messages"]
    assert sent[0]["role"] == "system" and "<data source=" not in sent[0]["content"]
    assert 'source="evidence"' in sent[1]["content"] and "value_hypothesis" in sent[1]["content"]


def test_invalid_output_is_corrected_then_counts_as_a_failed_attempt(model_harness: Any) -> None:
    h, late = model_harness({PRIMARY: [reply(BAD), reply(BAD), reply(BAD), reply(GOOD)]})
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1").run_id
    first = attempts(h.app, t1)[0]
    assert (first["outcome"], first["corrections"], first["steps"]) == ("failed", 2, 3)
    assert "missing" in first["reason"] and "x" not in first["reason"].split("columns")[-1][:3]
    # SC-004: nothing from the failed attempt reached versions or controls.
    versions = h.sql("SELECT count(*) FROM run.artifact_version WHERE run_id = :r", r=t1)
    second = attempts(h.app, t1)[1]
    assert second["outcome"] == "artifacts" and second["attempt"] == 2
    assert versions[0][0] == len(load_synthetic_artifacts(SYNTHETIC)["T1"])
    assert h.run(t1).state == "awaiting_sign_off"


def test_failed_attempts_escalate_at_the_retry_limit(model_harness: Any) -> None:
    h, late = model_harness({PRIMARY: reply(BAD)})
    usecase, _ = walk_to(h, "T0")
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1")
    assert (t1.state, t1.escalation_trigger) == ("escalated", "retry_limit")
    assert {a["outcome"] for a in attempts(h.app, t1.run_id)} == {"failed"}
    assert (
        h.sql("SELECT count(*) FROM run.artifact_version WHERE run_id = :r", r=t1.run_id)[0][0] == 0
    )


@pytest.mark.parametrize(
    ("limit", "limits"),
    [
        ("steps", AgentLimit(steps=1, tokens=400_000, timeout_s=240)),
        ("tokens", AgentLimit(steps=8, tokens=50, timeout_s=240)),
        ("timeout", AgentLimit(steps=8, tokens=400_000, timeout_s=1e-9)),
    ],
)
def test_limits_escalate_with_the_limit_named(
    model_harness: Any, limit: str, limits: AgentLimit
) -> None:
    h, _ = model_harness(
        {PRIMARY: reply(BAD, tokens=(30, 30))},
        limits={**DEFAULT_AGENT_LIMITS, "reasoning": limits},
    )
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})  # one drain inside
    t1 = h.active(usecase, "T1")
    assert (t1.state, t1.escalation_trigger) == ("escalated", "budget")
    attempt = [a for a in attempts(h.app, t1.run_id) if a["kind"] == "build"][-1]
    assert (attempt["outcome"], attempt["limit_reached"]) == ("budget_exceeded", limit)


def test_refusals_are_retried_on_the_same_model_only(model_harness: Any) -> None:
    h, late = model_harness({PRIMARY: reply("", outcome="refusal", reason="content_filter")})
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1").run_id
    calls = model_calls(h.app, t1)
    assert {c["model"] for c in calls} == {PRIMARY}  # never another provider
    assert {c["outcome"] for c in calls} == {"refusal"}
    assert attempts(h.app, t1)[0]["outcome"] == "failed"


def test_full_outage_defers_then_escalates(model_harness: Any) -> None:
    down = {
        e.model: reply("", outcome="outage", reason="server") for e in MODELS.entries("reasoning")
    }
    h, late = model_harness(down)
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1")
    assert t1.state == "building" and t1.model_unavailable_since is not None
    assert t1.auto_retries == 0  # an outage never uses a retry
    deferred = h.sql(
        "SELECT count(*) FROM run.run_activity WHERE run_id = :r AND outcome = 'deferred'",
        r=t1.run_id,
    )
    assert deferred[0][0] == 1
    for _ in range(6):  # back-off: 30 s, 60 s, ... capped at 5 min
        h.clock.advance(timedelta(minutes=5, seconds=1))
        h.drain()
    run = h.run(t1.run_id)
    assert (run.state, run.escalation_trigger) == ("escalated", "model_unavailable")


def test_success_after_an_outage_clears_it(model_harness: Any) -> None:
    script: dict[str, Any] = {
        e.model: [reply("", outcome="outage", reason="server"), reply(GOOD)]
        for e in MODELS.entries("reasoning")
    }
    h, _ = model_harness(script)
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1").run_id
    assert h.run(t1).model_unavailable_since is not None
    h.clock.advance(timedelta(seconds=31))
    h.drain()
    run = h.run(t1)
    assert run.model_unavailable_since is None and run.state == "awaiting_sign_off"


def test_an_interrupted_step_keeps_its_model_calls(model_harness: Any) -> None:
    """A worker crash after a model call: the call stays recorded; the redone step completes."""
    crashed = {"done": False}

    def flaky(messages: Sequence[Mapping[str, str]]) -> ProviderReply:
        if not crashed["done"] and len(messages) > 2:  # the correction round
            crashed["done"] = True
            raise RuntimeError("worker crashed")
        return reply(BAD) if len(messages) == 2 else reply(GOOD)

    h, _ = model_harness({PRIMARY: flaky})
    usecase = h.submit()
    with pytest.raises(RuntimeError, match="worker crashed"):
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1").run_id
    assert [c["outcome"] for c in model_calls(h.app, t1)] == ["ok"]  # recorded before the crash
    h.clock.advance(timedelta(minutes=6))  # the lease expires
    h.drain()
    assert h.run(t1).state == "awaiting_sign_off"
    calls = model_calls(h.app, t1)
    assert len(calls) >= 3 and h.sql("SELECT calls FROM run.v_run_cost WHERE run_id = :r", r=t1)[0][
        0
    ] == len(calls)
