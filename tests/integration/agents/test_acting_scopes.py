"""011 T020 (US4; SC-006): acting agents act only through their own terminal's tools. A tool another
terminal holds is refused and recorded; arguments that would bind the call are ignored; nothing
out of scope reaches the pilot; the agent decides nothing."""

import json
from pathlib import Path

from sqlalchemy import text

from tests.support.acting import acting, tool
from tests.support.fake_pilot import FakePilot, with_candidate
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase

T3 = "t3-builder-agent"
T4 = "t4-evaluation-agent"
STOP = json.dumps(
    {
        "clarification": {
            "questions": ["Which team owns this?"],
            "looked_in": ["evidence"],
            "addressed_role": None,
        }
    }
)


def to(h: Harness, terminal: str) -> str:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for t in ("T1", "T2", "T3"):
        if t == terminal:
            break
        h.pass_run(h.active(usecase, t).run_id)
    return h.active(usecase, terminal).run_id


def calls(h: Harness, run_id: str) -> list[tuple[str, str, str]]:
    with h.app.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tool, outcome, reason FROM tools.tool_call WHERE run_id = :r ORDER BY tool_call_id"
            ),
            {"r": run_id},
        ).all()
    return [(str(a), str(b), str(c)) for a, b, c in rows]


def test_t3_cannot_choose_its_environment(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    fake = FakePilot()
    package = fake.add_package()
    replies = {
        T3: [tool("pilot_env_create", {"package_hash": package, "environment": "test"}), STOP]
    }
    with acting(orch_template, replies, (T3,), tmp_path, fake) as a:
        run_id = to(a.h, "T3")
        assert fake.hosts["dev"].running is not None and fake.hosts["test"].running is None
        assert calls(a.h, run_id) == [("pilot_env_create", "ok", "")]
        assert a.h.run(run_id).state == "awaiting_clarification"


def test_t4_cannot_use_t3_tools(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    fake = with_candidate(FakePilot())
    replies = {
        T4: [
            tool("git_write", {"files": {"instructions.md": "x"}, "message": "m"}),
            tool("cd_deploy"),
            STOP,
        ]
    }
    # T3 is a model agent too, so its tools are wired; T4 holds none of them.
    with acting(orch_template, replies, (T4,), tmp_path, fake) as a:
        run_id = to(a.h, "T4")
        recorded = calls(a.h, run_id)
        assert fake.builds == [] and not any(
            host.calls for host in fake.hosts.values()
        )  # nothing new
        assert (
            a.h.run(run_id).state == "awaiting_clarification"
        )  # the agent asked; it decided nothing
        # git_write is not wired (no model agent holds it here): refused without a system call
        assert recorded == []


# ------------------------------------------------------------------ 012 (US5)

T6, T7, T8 = "t6-readiness-agent", "t7-deployment-agent", "t8-operations-agent"


def to_late(h: Harness, terminal: str) -> str:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
        if t == terminal:
            break
        run = h.active(usecase, t)
        h.drain()
        h.pass_run(run.run_id)
    return h.active(usecase, terminal).run_id


def _released() -> FakePilot:
    from tests.support.fake_pilot import SYNTHETIC_CANDIDATE  # noqa: PLC0415

    fake = with_candidate(FakePilot(), "test")
    fake.hosts["prod-sim"].stable = SYNTHETIC_CANDIDATE
    return fake


def test_t6_cannot_deploy(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    fake = _released()
    replies = {T6: [tool("cd_deploy"), tool("traffic_manager_set", {"mode": "full"}), STOP], T7: []}
    with acting(orch_template, replies, (T6, T7), tmp_path, fake) as a:
        before = list(fake.hosts["prod-sim"].calls)
        run_id = to_late(a.h, "T6")
        recorded = calls(a.h, run_id)
        assert [(t, o) for t, o, _ in recorded] == [
            ("cd_deploy", "refused"),
            ("traffic_manager_set", "refused"),
        ]
        assert fake.hosts["prod-sim"].calls == before  # nothing reached prod-sim
        assert a.h.run(run_id).state == "awaiting_clarification"


def test_t7_deploys_only_the_authorised_package(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = _released()
    other = fake.add_package()
    replies = {T7: [tool("cd_deploy", {"package_hash": other}), STOP]}
    with acting(orch_template, replies, (T7,), tmp_path, fake) as a:
        run_id = to_late(a.h, "T7")
        from tests.support.fake_pilot import SYNTHETIC_CANDIDATE  # noqa: PLC0415

        assert fake.hosts["prod-sim"].candidate == SYNTHETIC_CANDIDATE != other
        assert [(t, o) for t, o, _ in calls(a.h, run_id)] == [("cd_deploy", "ok")]


def test_t8_cannot_raise_a_change_or_deploy(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = _released()
    replies = {
        T8: [
            tool("servicenow_change_create", {"summary": "x", "risk": "low"}),
            tool("cd_deploy"),
            STOP,
        ]
    }
    # only T8 acts here: tools no acting agent holds are not wired, so nothing is called
    with acting(orch_template, replies, (T8,), tmp_path, fake) as a:
        before = list(fake.hosts["prod-sim"].calls)
        run_id = to_late(a.h, "T8")
        assert calls(a.h, run_id) == []
        assert fake.hosts["prod-sim"].calls == before
        with a.h.app.connect() as conn:
            changes = conn.execute(
                text("SELECT count(*) FROM tools.enterprise_record WHERE system = 'servicenow'")
            ).scalar_one()
        assert changes == 0
        assert a.h.run(run_id).state == "awaiting_clarification"
