"""012 T028 (FR-011, SC-005; D-6, D-7): the reference use case replays offline to T9. T0-T2 come
from their recordings; T3-T9 act through the real tools over the fake pilot with scripted replies.
T5's kill-switch gap is accepted with a waiver; T6 waits for the change approval; T7 releases T3's
package in stages; after T8's first review the model swap lowers quality, the drift monitor
raises the event, and T9 classifies the change."""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from adlc.agents.replay import (
    Replayer,
    Report,
    UseCaseResult,
    load_references,
    markdown,
    read_recording,
)
from adlc.inbox.changes import ChangeService
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.acting import acting
from tests.support.acting_scripts import (
    Assurance,
    Deployment,
    Evaluation,
    Evolution,
    Operations,
    Readiness,
    t3_build,
)
from tests.support.fake_pilot import FakePilot
from tests.support.orchestration import Harness, person
from tests.support.pg import REPO_ROOT, PlatformDatabase

REFERENCE = next(
    r for r in load_references(REPO_ROOT / "data" / "reference_usecases") if r.until == "T9"
)
RECORDINGS = REPO_ROOT / "tests" / "fixtures" / "replays" / REFERENCE.id
AGENTS = (
    "t0-intake-agent",
    "t1-requirements-agent",
    "t2-architect-agent",
    "t3-builder-agent",
    "t4-evaluation-agent",
    "t5-assurance-agent",
    "t6-readiness-agent",
    "t7-deployment-agent",
    "t8-operations-agent",
    "t9-evolution-agent",
)


def replay_to_t9(
    orch_template: PlatformDatabase,
    tmp_path: Path,
    check: Callable[[Harness, UseCaseResult, FakePilot], None],
) -> None:
    """Replay the reference to T9 and run ``check`` while the harness is still open (013 reuses
    it for the journey)."""
    fake = FakePilot()
    replies = dict(read_recording(RECORDINGS))
    replies["t3-builder-agent"] = t3_build()
    replies["t4-evaluation-agent"] = Evaluation().script()
    replies["t5-assurance-agent"] = Assurance().script(retries=3)
    replies["t6-readiness-agent"] = Readiness().script()
    replies["t7-deployment-agent"] = Deployment().script()
    replies["t8-operations-agent"] = Operations().script()
    replies["t9-evolution-agent"] = Evolution().script()
    faults = {"model_swap": lambda: fake.traffic.update(routing_accuracy=0.6)}
    with acting(orch_template, replies, AGENTS, tmp_path, fake, knowledge=True) as a:
        h = a.h
        registry = SqlSpecRegistry(h.app)

        def drain() -> int:
            h.clock.advance(timedelta(minutes=1))  # the change window opens as people approve
            return h.drain()

        replayer = Replayer(
            h.service,
            h.orch.runs,
            drain,
            lambda role: [person(role)],
            changes=ChangeService(h.app, registry, h.service, h.clock),
            monitors=MonitorEvaluator(h.app, registry, h.orch.runs.policy, h.service, timedelta(0)),
            fault=lambda name: faults[name](),
        )
        check(h, replayer.run(REFERENCE), fake)


def _expected(h: Harness, result: UseCaseResult, fake: FakePilot) -> None:
    assert result.outcome == "completed", (
        result.outcome,
        [(t.terminal_id, t.state, t.blocking_failed) for t in result.terminals],
    )
    by_terminal = {t.terminal_id: t for t in result.terminals}
    assert list(by_terminal) == [f"T{n}" for n in range(10)]
    for terminal in ("T0", "T1", "T2", "T3", "T4", "T6", "T7", "T8", "T9"):
        assert by_terminal[terminal].ok, (terminal, by_terminal[terminal].blocking_failed)
    assert by_terminal["T5"].blocking_failed == ["CTL-T5-05"]  # accepted with a waiver
    t9 = h.active(result.usecase_id, "T9")
    assert t9.trigger_event_type == "T8.event.drift" and t9.mode == "evolve"
    assert (
        fake.hosts["prod-sim"].stable
        == h.run(by_terminal["T3"].run_id).artifacts["candidate_package"][0]["sha256"]
    )  # D-6
    assert all(by_terminal[t].tool_calls > 0 for t in ("T6", "T7", "T8", "T9"))
    assert "Tool calls" in markdown(Report("recording", None, [result]))


def test_reference_replays_to_t9(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    replay_to_t9(orch_template, tmp_path, _expected)
