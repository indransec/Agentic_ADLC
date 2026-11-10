"""T003: migration 0006 (data-model.md): prompt registry, agent attempts, model calls, costs."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.pg import PlatformDatabase, alembic

HASH = "sha256:" + "b" * 64
RUN_TABLES = ("run.agent_attempt", "run.model_call", "run.cost_alert")
VIEWS = ("run.v_run_cost", "run.v_terminal_cost", "run.v_usecase_cost")
RUN = "UC-0001/T1/run-1"


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO run.usecase (usecase_id, name, intake_text, submitted_by) VALUES ('UC-0001', 'n', 'i', 'o')",
            f"INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, spec_version, state, mode, trigger_event_type) VALUES ('{RUN}', 'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', 'T0.pass')",
            f"INSERT INTO run.agent_attempt (run_id, kind, attempt, agent_id, agent_version, implementation, playbook_hashes, context_hash, steps, tokens_in, tokens_out, corrections, outcome, started_at, ended_at) VALUES ('{RUN}', 'review', 1, 'common-terminal-reviewer', '1.0.0', 'model', '{{}}', '{HASH}', 2, 100, 20, 1, 'recommendation', now(), now())",
            f"INSERT INTO run.model_call (agent_attempt_ref, run_id, usecase_id, terminal_id, agent_id, tier, entry_index, provider, model, prompt_hash, context_hash, tokens_in, tokens_out, usage_estimated, cost_usd, cost_known, latency_ms, outcome, fallback, called_at) VALUES ('{RUN}/review/1', '{RUN}', 'UC-0001', 'T1', 'common-terminal-reviewer', 'reasoning', 1, 'openai', 'openai/gpt-4o-mini', '{HASH}', '{HASH}', 100, 20, false, 0.000027, true, 812, 'ok', false, now())",
            f"INSERT INTO run.model_call (agent_attempt_ref, run_id, usecase_id, terminal_id, agent_id, tier, entry_index, provider, model, prompt_hash, context_hash, tokens_in, tokens_out, usage_estimated, cost_usd, cost_known, latency_ms, outcome, reason, fallback, called_at) VALUES ('{RUN}/review/1', '{RUN}', 'UC-0001', 'T1', 'common-terminal-reviewer', 'reasoning', 2, 'gemini', 'gemini/x', '{HASH}', '{HASH}', 0, 0, false, NULL, false, 0, 'skipped', 'no_key', false, now())",
            "INSERT INTO run.cost_alert (usecase_id, level_usd, total_usd) VALUES ('UC-0001', 5, 5.1)",
        ):
            conn.execute(text(sql))


def test_grants(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_schema || '.' || table_name, privilege_type FROM "
                "information_schema.role_table_grants WHERE grantee = current_user"
            )
        ).all()
    grants: dict[str, set[str]] = {}
    for table, privilege in rows:
        grants.setdefault(table, set()).add(privilege)
    for table in RUN_TABLES:
        assert grants[table] == {"SELECT", "INSERT"}, table
    for view in VIEWS:
        assert grants[view] == {"SELECT"}, view
    assert grants["spec.prompt_registry"] == {"SELECT"}  # written by registration (owner)


def test_constraints(app_engine: Engine, owner_engine: Engine) -> None:
    _seed(app_engine)

    def attempt(
        kind: str = "'build'",
        n: str = "1",
        impl: str = "'stub'",
        outcome: str = "'artifacts'",
        limit: str = "NULL",
        reason: str = "NULL",
    ) -> str:
        return (
            "INSERT INTO run.agent_attempt (run_id, kind, attempt, agent_id, agent_version, "
            "implementation, playbook_hashes, context_hash, steps, tokens_in, tokens_out, "
            "corrections, outcome, limit_reached, reason, started_at, ended_at) VALUES "
            f"('{RUN}', {kind}, {n}, 'a', '1.0.0', {impl}, '{{}}', '{HASH}', 0, 0, 0, 0, "
            f"{outcome}, {limit}, {reason}, now(), now())"
        )

    bad_attempts = [
        attempt(kind="'judge'"),
        attempt(n="0"),
        attempt(impl="'llm'"),
        attempt(outcome="'passed'"),
        attempt(limit="'memory'"),
        attempt(reason="repeat('x', 2001)"),
    ]
    call = (
        "INSERT INTO run.model_call (agent_attempt_ref, run_id, usecase_id, terminal_id, agent_id, "
        "tier, entry_index, provider, model, prompt_hash, context_hash, tokens_in, tokens_out, "
        "usage_estimated, cost_usd, cost_known, latency_ms, outcome, fallback, called_at) VALUES "
        f"('r', '{RUN}', 'UC-0001', 'T1', 'a', 'reasoning', 1, 'openai', 'm', '{HASH}', '{HASH}', "
        "0, 0, false, NULL, false, 0, {outcome}, false, now())"
    )
    with app_engine.connect() as conn:
        conn.execute(text(attempt()))
        for sql in bad_attempts:
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))
        conn.execute(text(call.format(outcome="'outage'")))
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(text(call.format(outcome="'crashed'")))
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO run.cost_alert (usecase_id, level_usd, total_usd) VALUES ('UC-0001', 5, 6)"
                )
            )
        tried = conn.execute(text("SELECT tried FROM run.model_call LIMIT 1")).scalar_one()
        assert tried == []
    with owner_engine.connect() as conn:
        for trigger in ("model_unavailable", "reviewer_failed"):
            with conn.begin_nested():
                conn.execute(
                    text("UPDATE run.terminal_run SET escalation_trigger = :t WHERE run_id = :r"),
                    {"t": trigger, "r": RUN},
                )
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text(
                    f"UPDATE run.terminal_run SET escalation_trigger = 'bored' WHERE run_id = '{RUN}'"
                )
            )
        for sql in (
            f"INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) VALUES ('Bad_Id', '1.0.0', 'prompts/x.md', '{HASH}')",
            "INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) VALUES ('reviewer', '1.0', 'prompts/x.md', 'md5:x')",
        ):
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))
        conn.execute(
            text(
                "INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) "
                f"VALUES ('common-terminal-reviewer', '1.0.0', 'prompts/r.md', '{HASH}')"
            )
        )
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) "
                    f"VALUES ('common-terminal-reviewer', '1.0.0', 'prompts/r.md', '{HASH}')"
                )
            )


def test_append_only(app_engine: Engine, owner_engine: Engine) -> None:
    _seed(app_engine)
    with owner_engine.begin() as conn:  # registration writes prompts as the owner
        conn.execute(
            text(
                "INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) "
                f"VALUES ('common-terminal-reviewer', '1.0.0', 'prompts/r.md', '{HASH}')"
            )
        )
    for engine in (app_engine, owner_engine):
        with engine.connect() as conn:
            for table in (*RUN_TABLES, "spec.prompt_registry"):
                for sql in (f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(sql))
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text("UPDATE run.model_call SET tokens_in = 1"))


def test_cost_views(app_engine: Engine) -> None:
    _seed(app_engine)
    with app_engine.connect() as conn:
        run = conn.execute(text("SELECT * FROM run.v_run_cost")).mappings().one()
        terminal = conn.execute(text("SELECT * FROM run.v_terminal_cost")).mappings().one()
        usecase = conn.execute(text("SELECT * FROM run.v_usecase_cost")).mappings().one()
    assert (run["run_id"], run["calls"], run["tokens_in"], run["tokens_out"]) == (RUN, 1, 100, 20)
    assert float(run["cost_usd"]) == pytest.approx(0.000027)
    assert (run["unknown_cost_calls"], run["fallback_answers"]) == (0, 0)
    assert (terminal["usecase_id"], terminal["terminal_id"], terminal["calls"]) == (
        "UC-0001",
        "T1",
        1,
    )
    assert (usecase["usecase_id"], usecase["calls"]) == ("UC-0001", 1)


def test_columns_added(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns WHERE "
                "table_schema = 'run' AND table_name = 'terminal_run' "
                "AND column_name = 'model_unavailable_since'"
            )
        ).one()
    assert tuple(row) == ("timestamp with time zone", "YES")


def test_round_trip(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0005")
    alembic(migrated_db, "upgrade", "head")
