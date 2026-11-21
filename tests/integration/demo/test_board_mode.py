"""020 T013 (US1, US3, US4; FR-001 to FR-007; SC-002, SC-003): the demo script driven on the board.

The platform and agents as in 014's auto test (rehearsed replies, the fake pilot); between the
platform and the driver, 016's projector and inbound sync over the fake board. Every human step is
a board change by the named demo person; D-12 and D-13 are shown; with the sync off (014's test)
the board-only steps are skipped.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from demo.rehearsed.replies import replies as rehearsed

from adlc.agents.replay import Replayer, load_references, read_recording
from adlc.demo.board import BoardActor, Write
from adlc.demo.driver import DemoDriver, DemoReport
from adlc.demo.script import BOARD_MOMENTS, MOMENTS, load_script
from adlc.engagement.model import ItemWrite
from adlc.identity.catalogue import load_role_ids
from adlc.inbox.changes import ChangeService
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.integration.demo.test_demo_auto import AGENTS, SCRIPT, TestIo
from tests.support.acting import acting
from tests.support.board import Rig, board_user
from tests.support.db import REPO_ROOT, PlatformDatabase
from tests.support.fake_pilot import FakePilot
from tests.support.orchestration import Harness, person


def _role(actor: Any) -> str:
    return str(actor.account_name).removesuffix("-person")


@contextmanager
def board_demo(
    orch_template: PlatformDatabase, tmp_path: Path, *, auto: bool = True
) -> Iterator[tuple[Harness, Rig, DemoDriver, TestIo]]:
    fake = FakePilot()
    replies = {**read_recording(REPO_ROOT / "demo" / "recordings"), **rehearsed()}
    with acting(orch_template, replies, AGENTS, tmp_path, fake, knowledge=True) as a:
        h = a.h
        rig = Rig(h)
        registry = SqlSpecRegistry(h.app)

        def drain() -> int:
            h.clock.advance(timedelta(minutes=1))  # the change window opens as people approve
            moved = h.drain()
            rig.projector.run_once()
            rig.sync.poll()  # people's board changes become platform requests
            moved += h.drain()
            rig.projector.run_once()
            return moved

        actor = BoardActor(
            h.app,
            rig.mapping,
            adapter_for=lambda who: rig.board.as_user(board_user(_role(who))),
            user_of=lambda who: board_user(_role(who)),
            service_board=rig.board,
            wait=lambda: None if drain() < 0 else None,
            rounds=60,
        )
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
            auto=auto,
            rounds=60,
            board=actor,
            reconcile=lambda: rig.reconciler().reconcile(person("adlc_coe")),
        )
        yield h, rig, driver, io


def _sources(h: Harness) -> list[dict[str, Any]]:
    details = [
        r[0] if isinstance(r[0], dict) else json.loads(r[0])
        for r in h.sql("SELECT detail FROM run_activity WHERE detail LIKE '%board_item%'")
    ]
    return [d["source"] for d in details if "source" in d]


def test_the_demo_runs_on_the_board(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    with board_demo(orch_template, tmp_path) as (h, rig, driver, io):
        report: DemoReport = driver.run()
        failed = [(s.number, s.outcome) for s in report.steps if s.outcome != "ok"]
        assert report.ok, (failed, io.said[-4:])
        assert [s.number for s in report.steps] == list(range(1, 18))
        moments = report.moments()
        for moment in (*MOMENTS, *sorted(BOARD_MOMENTS)):
            assert moments.get(moment), moment
        assert "NOT SHOWN" not in report.markdown()
        # SC-002: every human step was a board change by a demo person, read by the sync
        writes = driver.board.log if driver.board else []
        assert writes and all(w["person"].endswith("@board.test") for w in writes)
        assert {w["kind"] for w in writes} >= {"usecase", "run", "clarification", "change"}
        assert _sources(h)  # the platform recorded where the decisions came from
        # D-12 and D-13 with their evidence
        d12 = next(s for s in report.steps if s.number == 16).evidence
        assert d12["restored"] != d12["attempted"]
        d13 = next(s for s in report.steps if s.number == 17).evidence
        assert d13["corrected"]["value"] != "Closed" and d13["differences"] >= 1


def test_presenter_mode_names_the_item_and_the_values(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    """The presenter is told who, where and what; here the test plays the presenter."""
    with board_demo(orch_template, tmp_path, auto=False) as (_, _, driver, io):
        assert driver.board is not None
        board = driver.board
        pending: list[Write] = []
        told = board.instruction

        def instruction(write: Write) -> str:
            pending.append(write)
            return told(write)

        board.instruction = instruction  # type: ignore[method-assign]

        def pause() -> None:  # the presenter does what was said, on the board
            while pending:
                board.adapter_for(pending[0].actor).update(
                    board.item(pending[0].kind, pending[0].object_id),
                    ItemWrite(set=dict(pending.pop(0).fields)),
                )

        io.pause = pause  # type: ignore[method-assign]
        driver.auto = True  # the use case is created by the driver; then presenter steps
        driver._submit(driver.script.steps[0], driver.script.steps[0].actions[0])  # noqa: SLF001
        driver.auto = False
        run = driver._wait_for_people(driver.script.steps[0])  # noqa: SLF001
        driver._board_act(run, driver.script.steps[0].actions[1])  # noqa: SLF001
        said = [t for t in io.said if t.startswith("As ")]
        assert said and "http://board.test/items/" in said[0]
        assert "decision = 'Pass'" in said[0] and "risk_tier: low" in said[0]
        after = driver.service.get_run(run.run_id)
        assert after is not None and after.final_status == "pass"
