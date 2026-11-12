"""Records of tool calls and evidence results (feature 010, data-model.md, research R-04).

Written by the platform, never by the agent or a server: ``tools.tool_call`` for every call
(including refusals) and ``tools.tool_result`` for an evidence tool's answer, with its content hash.
Both tables are append-only.
"""

from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.expression import bindparam

from adlc.agents.imports import ImportSource, Resolver
from adlc.agents.mcp_tools import sha256_of
from adlc.agents.tools import ToolContext
from adlc.orchestration.interfaces import Clock
from adlc.tools.catalogue import ToolSpec


class SqlToolRecords:
    def __init__(self, engine: Engine, clock: Clock) -> None:
        self.engine, self.clock = engine, clock

    def call(
        self,
        context: ToolContext,
        tool: ToolSpec,
        scope: str,
        arguments_sha256: str,
        outcome: str,
        reason: str,
        duration_ms: int,
    ) -> int:
        with self.engine.begin() as conn:
            return int(
                conn.execute(
                    text(
                        "INSERT INTO tools.tool_call (run_id, usecase_id, terminal_id, attempt, "
                        "step, tool, server, scope, arguments_sha256, outcome, reason, "
                        "duration_ms, at) VALUES (:run, :uc, :t, :attempt, :step, :tool, "
                        ":server, :scope, :args, :outcome, :reason, :ms, :at) "
                        "RETURNING tool_call_id"
                    ),
                    {
                        "run": context.run_id,
                        "uc": context.usecase_id,
                        "t": context.terminal_id,
                        "attempt": max(1, context.attempt),
                        "step": max(0, context.step),
                        "tool": tool.full_name,
                        "server": tool.server,
                        "scope": scope,
                        "args": arguments_sha256,
                        "outcome": outcome,
                        "reason": reason[:2000],
                        "ms": duration_ms,
                        "at": self.clock.now(),
                    },
                ).scalar_one()
            )

    def result(
        self, call_id: int, context: ToolContext, kind: str, package: str | None, result: Any
    ) -> str:
        with self.engine.begin() as conn:
            found = conn.execute(
                text(
                    "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, "
                    "terminal_id, kind, package_hash, result, result_sha256, at) VALUES (:call, "
                    ":run, :uc, :t, :kind, :package, :result, :sha, :at) RETURNING tool_result_id"
                ).bindparams(bindparam("result", type_=JSONB)),
                {
                    "call": call_id,
                    "run": context.run_id,
                    "uc": context.usecase_id,
                    "t": context.terminal_id,
                    "kind": kind,
                    "package": package,
                    "result": result,
                    "sha": sha256_of(result),
                    "at": self.clock.now(),
                },
            ).scalar_one()
        return f"RES-{found}"


def case_results(engine: Engine, run_id: str) -> Resolver:
    """011: the run's recorded results that offer case rows, for table imports (R-08)."""

    def resolve(result_id: str) -> ImportSource | None:
        if not result_id.startswith("RES-") or not result_id[4:].isdigit():
            return None
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT kind, result, result_sha256 FROM tools.tool_result "
                    "WHERE tool_result_id = :id AND run_id = :run"
                ),
                {"id": int(result_id[4:]), "run": run_id},
            ).first()
        if row is None or not isinstance(row[1], dict) or not isinstance(row[1].get("cases"), list):
            return None
        return ImportSource(result_id, str(row[0]), str(row[2]), list(row[1]["cases"]))

    return resolve
