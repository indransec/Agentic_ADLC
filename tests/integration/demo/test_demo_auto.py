"""014 T008 (US1; FR-001 to FR-003; SC-002): the demo script runs end to end in --auto over the
fake pilot with the rehearsed replies (recordings for the writing agents, reply programs for the
acting ones); the report shows D-1 to D-9 each with evidence. The test plays the host wrapper:
it applies the pilot faults the driver asks for."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from demo.rehearsed.replies import replies as rehearsed

from adlc.agents.replay import Replayer, load_references, read_recording
from adlc.demo.driver import DemoDriver, DemoReport
from adlc.demo.script import MOMENTS, load_script
from adlc.identity.catalogue import load_role_ids
from adlc.inbox.changes import ChangeService
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.acting import acting
from tests.support.fake_pilot import FakePilot
from tests.support.orchestration import Harness, person
from tests.support.pg import REPO_ROOT, PlatformDatabase

SCRIPT = REPO_ROOT / "demo" / "script.yaml"
AGENTS = tuple(
    f"t{n}-{a}"
    for n, a in enumerate(
        (
            "intake-agent",
            "requirements-agent",
            "architect-agent",
            "builder-agent",
            "evaluation-agent",
            "assurance-agent",
            "readiness-agent",
            "deployment-agent",
            "operations-agent",
            "evolution-agent",
        )
    )
)


@dataclass
class TestIo:
    pilot: FakePilot
    said: list[str] = field(default_factory=list)
    faults: list[tuple[str, str]] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.said.append(text)

    def fault(self, name: str, action: str) -> None:  # what scripts/demo.py does with pilot-fault
        self.faults.append((name, action))
        if name == "model_swap":
            self.pilot.traffic["routing_accuracy"] = 0.6 if action == "trigger" else 0.97

    def pause(self) -> None:
        return None


@contextmanager
def demo(
    orch_template: PlatformDatabase, tmp_path: Path
) -> Iterator[tuple[Harness, DemoDriver, TestIo]]:
    fake = FakePilot()
    replies = {**read_recording(REPO_ROOT / "demo" / "recordings"), **rehearsed()}
    with acting(orch_template, replies, AGENTS, tmp_path, fake, knowledge=True) as a:
        h = a.h
        registry = SqlSpecRegistry(h.app)

        def drain() -> int:
            h.clock.advance(timedelta(minutes=1))  # the change window opens as people approve
            return h.drain()

        replayer = Replayer(h.service, h.orch.runs, drain, lambda role: [person(role)])
        io = TestIo(fake)
        script = load_script(
            SCRIPT, load_role_ids(REPO_ROOT / "adlc-specs" / "shared" / "roles.yaml")
        )
        references = {r.id: r for r in load_references(REPO_ROOT / "data" / "reference_usecases")}
        driver = DemoDriver(
            script,
            references,
            replayer,
            ChangeService(h.app, registry, h.service, h.clock),
            MonitorEvaluator(h.app, registry, h.orch.runs.policy, h.service, timedelta(0)),
            io,
            auto=True,
            rounds=40,
        )
        yield h, driver, io


def test_the_demo_runs_end_to_end(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    with demo(orch_template, tmp_path) as (_, driver, io):
        report: DemoReport = driver.run()
        failed = [(s.number, s.outcome) for s in report.steps if s.outcome != "ok"]
        assert report.ok, (failed, io.said[-3:])
        assert [s.number for s in report.steps] == list(range(1, 16))
        moments = report.moments()
        assert all(moments[m] for m in MOMENTS), {m: v for m, v in moments.items() if not v}
        assert io.faults == [("model_swap", "trigger"), ("model_swap", "revert")]
        reroute = next(s for s in report.steps if s.number == 6).evidence["arrow"]
        assert reroute["kind"] == "reroute" and reroute["to_run"].endswith("/T3/run-2")
        assert next(s for s in report.steps if s.number == 15).evidence["trigger"] == "rework_limit"
        assert "NOT SHOWN" not in report.markdown()
