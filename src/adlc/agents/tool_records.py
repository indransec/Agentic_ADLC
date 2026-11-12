"""Records of tool calls and evidence results (feature 010, data-model.md, research R-04).

Written by the platform, never by the agent or a server: ``tools.tool_call`` for every call
(including refusals) and ``tools.tool_result`` for an evidence tool's answer, with its content hash.
Both tables are append-only.
"""

from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.expression import bindparam

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
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, "
                    "terminal_id, kind, package_hash, result, result_sha256, at) VALUES (:call, "
                    ":run, :uc, :t, :kind, :package, :result, :sha, :at)"
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
            )
