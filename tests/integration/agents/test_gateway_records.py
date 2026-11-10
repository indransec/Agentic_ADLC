"""T017: gateway records land in run.model_call, one row per request, with tried and cost."""

from datetime import UTC, datetime
from decimal import Decimal

from adlc.agents.catalogue import ModelCatalogue
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import CallIds, ModelRequest
from adlc.agents.store import SqlCallRecorder, insert_attempt, model_calls
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

ENTRY = {
    "input_per_mtok": 1.0,
    "output_per_mtok": 2.0,
    "max_output_tokens": 50,
    "context_tokens": 1000,
    "max_data_class": "confidential_masked",
}
CATALOGUE = ModelCatalogue.from_content(
    {
        "profiles": {
            "default": {
                "reasoning": [
                    {"provider": "anthropic", "model": "anthropic/m1", **ENTRY},
                    {"provider": "openai", "model": "openai/m2", **ENTRY},
                ]
            }
        }
    },
    "default",
    {"internal": 2, "confidential_masked": 4},
)


def test_rows_with_tried_and_cost(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    gateway = FakeGateway(
        CATALOGUE,
        {
            "anthropic/m1": reply("", outcome="outage", reason="rate_limit"),
            "openai/m2": reply("ok", tokens=(1000, 500)),
        },
        recorder=SqlCallRecorder(h.app),
    )
    ids = CallIds(run_id, usecase, "T1", "t1-requirements-agent", f"{run_id}/build/1")
    request = ModelRequest(
        "reasoning",
        "internal",
        ({"role": "user", "content": "x"},),
        100,
        9.0,
        ids,
        None,
        "sha256:" + "d" * 64,
    )
    response = gateway.complete(request)
    assert response.fallback and response.model == "openai/m2"
    rows = model_calls(h.app, run_id)
    assert [(r["model"], r["outcome"], r["fallback"]) for r in rows] == [
        ("anthropic/m1", "outage", False),
        ("openai/m2", "ok", True),
    ]
    assert rows[1]["tried"] == [
        {"model": "anthropic/m1", "outcome": "outage", "reason": "rate_limit"}
    ]
    assert rows[1]["cost_usd"] == Decimal("0.002000") and rows[0]["cost_usd"] == Decimal("0")
    now = datetime.now(UTC)
    insert_attempt(
        h.app,
        {
            "run_id": run_id,
            "kind": "build",
            "attempt": 1,
            "agent_id": "t1-requirements-agent",
            "agent_version": "1.0.0",
            "implementation": "model",
            "prompt_hash": None,
            "context_hash": "sha256:" + "d" * 64,
            "steps": 2,
            "tokens_in": 1000,
            "tokens_out": 500,
            "cost_usd": Decimal("0.002"),
            "corrections": 0,
            "outcome": "artifacts",
            "limit_reached": None,
            "reason": "x" * 3000,
            "started_at": now,
            "ended_at": now,
            "playbook_hashes": {"PB-T1-01": "sha256:" + "e" * 64},
        },
    )
    view = h.sql(
        "SELECT calls, fallback_answers, cost_usd FROM run.v_run_cost WHERE run_id = :r", r=run_id
    )
    assert tuple(view[0]) == (1, 1, Decimal("0.002000"))
