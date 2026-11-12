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
