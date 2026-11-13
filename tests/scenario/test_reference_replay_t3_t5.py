"""011 T023 (US5; FR-013, SC-001): the reference use case that matches the pilot's golden template
replays from T0 to T5 sign-off: T0-T2 from their recordings, T3-T5 acting through the real tools
over the fake pilot; the report counts tool calls; the T5 kill-switch gap is completed by a person
and left for the approvers to decide."""

from dataclasses import replace
from pathlib import Path

from adlc.agents.replay import Replayer, Report, load_references, markdown, read_recording
from tests.support.acting import acting
from tests.support.acting_scripts import Assurance, Evaluation, t3_build
from tests.support.orchestration import person
from tests.support.pg import REPO_ROOT, PlatformDatabase

# 012: the reference now runs to T9; this test keeps the 011 scope (to T5's sign-off)
REFERENCE = replace(
    next(
        r
        for r in load_references(REPO_ROOT / "data" / "reference_usecases")
        if r.id == "it-service-desk"
    ),
    until="T5",
)
RECORDINGS = REPO_ROOT / "tests" / "fixtures" / "replays" / REFERENCE.id
AGENTS = (
    "t0-intake-agent",
    "t1-requirements-agent",
    "t2-architect-agent",
    "t3-builder-agent",
    "t4-evaluation-agent",
    "t5-assurance-agent",
)


def test_reference_replays_through_the_acting_terminals(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    replies = dict(read_recording(RECORDINGS))
    replies["t3-builder-agent"] = t3_build()
    replies["t4-evaluation-agent"] = Evaluation().script()
    replies["t5-assurance-agent"] = Assurance().script(retries=3)
    with acting(orch_template, replies, AGENTS, tmp_path, knowledge=True) as a:
        result = Replayer(a.h.service, a.h.orch.runs, a.h.drain, lambda role: [person(role)]).run(
            REFERENCE
        )
    assert result.outcome == "completed", result.outcome
    by_terminal = {t.terminal_id: t for t in result.terminals}
    assert list(by_terminal) == ["T0", "T1", "T2", "T3", "T4", "T5"]
    for terminal in ("T0", "T1", "T2", "T3", "T4"):
        assert by_terminal[terminal].ok, (terminal, by_terminal[terminal].blocking_failed)
    assert by_terminal["T5"].blocking_failed == ["CTL-T5-05"]  # the kill switch, decided by people
    assert (
        by_terminal["T5"].state == "awaiting_sign_off" and not by_terminal["T5"].mandatory_missing
    )
    assert [by_terminal[t].tool_calls for t in ("T3", "T4", "T5")] == [6, 4, 6]
    assert by_terminal["T0"].tool_calls == 0
    report = markdown(Report("recording", None, [result]))
    assert "Tool calls" in report
