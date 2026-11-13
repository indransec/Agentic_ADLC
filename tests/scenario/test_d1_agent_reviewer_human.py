"""014 T011 (D-1): at every terminal an agent built, the reviewer recommended (or, after an
escalation, a person completed the run) and a person decided, each recorded (the demo script in
--auto)."""

from pathlib import Path

from tests.scenario.demo_run import demo_run
from tests.support.pg import PlatformDatabase


def test_d1_at_every_terminal(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    with demo_run(orch_template, tmp_path) as d:
        rows = d.h.sql(
            "SELECT r.terminal_id, "
            "bool_or(EXISTS (SELECT 1 FROM run.agent_attempt a WHERE a.run_id = r.run_id "
            "AND a.kind = 'build')), "
            "bool_or(r.recommendation IS NOT NULL), "
            "bool_or(EXISTS (SELECT 1 FROM run.sign_off s WHERE s.run_id = r.run_id)) "
            "FROM run.terminal_run r WHERE r.usecase_id = :u GROUP BY r.terminal_id",
            u=d.main,
        )
        found = {str(t): (bool(b), bool(rec), bool(s)) for t, b, rec, s in rows}
        assert sorted(found) == [f"T{n}" for n in range(10)]
        # a run a person completed after an escalation goes to sign-off without a review (003
        # design): D-1's reviewer step is then the person's completion, recorded as such
        no_review = {t for t, v in found.items() if not v[1]}
        completed = {
            str(t)
            for (t,) in d.h.sql(
                "SELECT DISTINCT r.terminal_id FROM run.run_transition x JOIN run.terminal_run r "
                "USING (run_id) WHERE r.usecase_id = :u AND x.signal_kind = 'escalation_completed'",
                u=d.main,
            )
        }
        assert no_review <= completed, (no_review, completed)
        assert all(v[0] and v[2] for v in found.values()), found
        people = d.h.sql(
            "SELECT DISTINCT s.person FROM run.sign_off s JOIN run.terminal_run r USING (run_id) "
            "WHERE r.usecase_id = :u",
            u=d.main,
        )
        assert all(str(p[0]).endswith("-person") for p in people)  # people, never agents
