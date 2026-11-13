"""012 (research R-06): the run's observability readings keyed by the rollout stage set before."""

from typing import Any

from sqlalchemy import Engine, text

from adlc.policy import tool_evidence
from tests.integration.tools.test_migration_0009 import _call

UC, RUN = "UC-0001", "UC-0001/T7/run-1"


def _result(engine: Engine, kind: str, result: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, terminal_id, "
                "kind, package_hash, result, result_sha256, at) SELECT tool_call_id, :r, :u, "
                f"'T7', '{kind}', NULL, CAST(:res AS jsonb), 'sha256:{'d' * 64}', now() "
                "FROM tools.tool_call LIMIT 1"
            ),
            {"r": RUN, "u": UC, "res": result},
        )


def _stages(engine: Engine, run: str = RUN) -> Any:
    with engine.connect() as conn:
        return tool_evidence.read(conn, "observability", UC, run, lambda: None)


def test_metrics_are_keyed_by_the_stage_set_before(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(text(_call()))
    assert _stages(app_engine) is None
    _result(app_engine, "observability", '{"metrics": {"routing_accuracy": 0.95}}')
    _result(app_engine, "traffic", '{"mode": "shadow"}')
    _result(app_engine, "observability", '{"metrics": {"routing_accuracy": 0.94, "cost": null}}')
    _result(app_engine, "traffic", '{"mode": "canary", "share": 0.1}')
    _result(app_engine, "observability", '{"metrics": {"routing_accuracy": 0.6}}')
    _result(app_engine, "traffic", '{"restored_stable": null, "mode": "full"}')
    _result(app_engine, "observability", '{"metrics": {"routing_accuracy": 0.95}}')
    assert _stages(app_engine) == {
        "stages": {
            "before:routing_accuracy": 0.95,
            "shadow:routing_accuracy": 0.94,
            "canary:routing_accuracy": 0.6,
            "rollback:routing_accuracy": 0.95,
        },
        "latest": {"routing_accuracy": 0.95},
    }
    assert _stages(app_engine, "UC-0001/T7/run-2") is None  # another run's readings are not read
