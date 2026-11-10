"""T030: the model reviewer in the orchestrator (US3; FR-016 to FR-018; SC-006)."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import ProviderReply
from adlc.agents.store import SqlCallRecorder, attempts
from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.lifecycle import walk_to
from tests.support.orchestration import SYNTHETIC, Harness, harness, person
from tests.support.pg import PlatformDatabase

from .test_runtime import MODELS, PRIMARY, _model_t1

ITEMS = ["CHK-T1-01", "CHK-T1-02", "CHK-T1-03", "CHK-T1-04", "CHK-T1-05"]
MARKER = "BUILDER-REASONING-MARKER-7731"
GOOD_BUILD = json.dumps({"artifacts": load_synthetic_artifacts(SYNTHETIC)["T1"]})


ITEM_LINE = re.compile(r"^- (CHK-[A-Za-z0-9-]+):", re.MULTILINE)


def _items(messages: Sequence[Mapping[str, str]]) -> list[str]:
    return ITEM_LINE.findall(messages[1]["content"])


def _review(
    status: str = "rework", cause: str | None = "requirement", items: Sequence[str] = ITEMS
) -> str:
    return json.dumps(
        {
            "scores": {i: 2 for i in items},
            "findings": [{"item": items[-2], "text": "KPI-02 target not supported"}],
            "recommendation": {
                "status": status,
                "reason": "Targets unrealistic",
                "root_cause": cause,
            },
        }
    )


Script = Callable[[Sequence[Mapping[str, str]]], ProviderReply]


def _router(review: Script, build: Script | None = None) -> Script:
    """One reasoning model serves builder and reviewer: route on the checklist block."""

    def route(messages: Sequence[Mapping[str, str]]) -> ProviderReply:
        if 'source="checklist"' in messages[-1]["content"] or any(
            'source="checklist"' in m["content"] for m in messages
        ):
            return review(messages)
        return build(messages) if build else reply(GOOD_BUILD)

    return route


@pytest.fixture
def reviewing(orch_template: PlatformDatabase) -> Any:
    opened: list[Any] = []

    def make(
        review: Script,
        *,
        build: Script | None = None,
        model_builder: bool = False,
        mode: str = "model",
    ) -> tuple[Harness, FakeGateway]:
        class Late:
            gateway: FakeGateway | None = None

            def complete(self, request: Any) -> Any:
                assert self.gateway is not None
                return self.gateway.complete(request)

        late = Late()
        kwargs: dict[str, Any] = {"gateway": late, "reviewer_mode": mode}
        if model_builder:
            kwargs["agents"] = _model_t1()
        ctx = harness(orch_template, **kwargs)
        h = ctx.__enter__()
        opened.append(ctx)
        late.gateway = FakeGateway(
            MODELS, {PRIMARY: _router(review, build)}, recorder=SqlCallRecorder(h.app)
        )
        return h, late.gateway

    yield make
    for ctx in opened:
        ctx.__exit__(None, None, None)


def test_review_scores_every_item_and_is_recorded(reviewing: Any) -> None:
    def answer(m: Sequence[Mapping[str, str]]) -> ProviderReply:
        items = _items(m)
        return reply(_review(items=items) if "CHK-T1-01" in items else _review("pass", None, items))

    h, gateway = reviewing(answer)
    usecase, t1 = walk_to(h, "T1")
    run = h.run(t1)
    assert run.state == "awaiting_sign_off"
    rec = run.recommendation
    assert (rec["status"], rec["reason"], rec["root_cause"], rec["reviewer"]) == (
        "rework",
        "Targets unrealistic",
        "requirement",
        "model",
    )
    assert rec["checklist_scores"] == {i: 2 for i in ITEMS}
    rows = h.sql(
        "SELECT item_id, score, finding FROM run.checklist_result WHERE run_id = :r "
        "ORDER BY checklist_result_id",
        r=t1,
    )
    assert len(rows) == 5 and ("CHK-T1-04", 2, "KPI-02 target not supported") in [
        tuple(r) for r in rows
    ]
    review = [a for a in attempts(h.app, t1) if a["kind"] == "review"]
    assert [(a["implementation"], a["outcome"], a["attempt"]) for a in review] == [
        ("model", "recommendation", 1)
    ]
    for role in ("product_owner", "business_owner"):  # passing against a rework needs a reason
        h.service.decide(person(role), t1, "pass", reason="targets agreed with finance")
    h.drain()
    record = h.sql("SELECT content_json FROM ledger.ledger_record WHERE run_id = :r", r=t1)[0][0]
    assert record["reviewer_recommendation"]["root_cause"] == "requirement"


def test_reviewer_never_sees_the_builders_messages(reviewing: Any) -> None:
    """SC-006: the builder's prompt, messages and corrections never reach the reviewer."""
    turns = {"n": 0}

    def build(messages: Sequence[Mapping[str, str]]) -> ProviderReply:
        turns["n"] += 1
        if turns["n"] == 1:  # an unfit first answer, so a correction round happens too
            return reply(f"{MARKER} " + json.dumps({"artifacts": {"kpis": [{"kpi": MARKER}]}}))
        return reply(GOOD_BUILD)

    h, gateway = reviewing(
        lambda m: reply(_review("pass", None, _items(m))), build=build, model_builder=True
    )
    walk_to(h, "T1")
    builder_requests = [
        c for c in gateway.fake.calls if 'source="checklist"' not in c["messages"][1]["content"]
    ]
    review_requests = [c for c in gateway.fake.calls if c not in builder_requests]
    assert len(builder_requests) == 2
    t1_reviews = [c for c in review_requests if "CHK-T1-01" in c["messages"][1]["content"]]
    assert len(t1_reviews) == 1
    sent = json.dumps(t1_reviews[0]["messages"])
    assert MARKER not in sent
    assert "did not fit the required shape" not in sent  # no builder correction rounds
    assert builder_requests[0]["messages"][0]["content"] not in [
        m["content"] for m in t1_reviews[0]["messages"][1:]
    ]


def test_unfit_review_escalates_reviewer_failed(reviewing: Any) -> None:
    h, _ = reviewing(lambda m: reply(_review("terminate", None)))
    usecase = h.submit()
    t0 = h.active(usecase, "T0")
    assert (t0.state, t0.escalation_trigger) == ("escalated", "reviewer_failed")
    review = [a for a in attempts(h.app, t0.run_id) if a["kind"] == "review"][0]
    assert (review["outcome"], review["corrections"]) == ("failed", 2)
    # People can still complete and decide the escalated run.
    h.service.complete_escalation(person("business_owner"), t0.run_id, {})
    assert h.run(t0.run_id).state == "awaiting_sign_off"


def test_reviewer_clarification_pauses_the_run(reviewing: Any) -> None:
    ask = json.dumps(
        {
            "clarification": {
                "questions": ["Which KPI baseline period applies?"],
                "addressed_role": "product_owner",
                "looked_in": ["kpis", "T0 evidence"],
            }
        }
    )
    h, _ = reviewing(
        lambda m: (
            reply(ask) if "CHK-T1-01" in _items(m) else reply(_review("pass", None, _items(m)))
        )
    )
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1")
    assert (t1.state, t1.return_state) == ("awaiting_clarification", "reviewing")
    row = h.sql(
        "SELECT asked_by, addressed_role, looked_in FROM run.clarification_round WHERE run_id = :r",
        r=t1.run_id,
    )[0]
    assert tuple(row) == ("reviewer", "product_owner", ["kpis", "T0 evidence"])


def test_stub_mode_is_recorded(reviewing: Any) -> None:
    h, gateway = reviewing(lambda m: reply(_review(items=_items(m))), mode="stub")
    usecase, t1 = walk_to(h, "T1")
    review = [a for a in attempts(h.app, t1) if a["kind"] == "review"]
    assert [a["implementation"] for a in review] == ["stub"]
    assert h.run(t1).recommendation["reviewer"] == "stub"
    assert gateway.fake.calls == []  # no model calls in stub mode
