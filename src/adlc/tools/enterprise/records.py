"""The enterprise mocks' records in ``tools.enterprise_record`` and the evidence results the eval
store reads from ``tools.tool_result`` (feature 010, data-model.md). Append-only: a change is a new
version; the highest version is current. Every record belongs to the use case of the run token."""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import bindparam

from adlc.tools.mcp_app import ToolFailure
from adlc.tools.token import Claims

EVIDENCE_KINDS = ("harness", "redteam", "dlp")
SUMMARY_DROP = ("rows", "cases", "findings")  # long per-row lists stay in tools.tool_result
TRIES = 5


class EnterpriseStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(
        self, system: str, kind: str, prefix: str, claims: Claims, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        for _ in range(TRIES):  # the id is the next number; a concurrent writer retries
            try:
                with self.engine.begin() as conn:
                    count = conn.execute(
                        text(
                            "SELECT count(DISTINCT record_id) FROM tools.enterprise_record "
                            "WHERE system = :s AND record_id LIKE :p"
                        ),
                        {"s": system, "p": f"{prefix}-%"},
                    ).scalar_one()
                    record_id = f"{prefix}-{int(count) + 1}"
                    self._insert(conn, system, kind, record_id, 1, claims, body)
                    return {**body, "id": record_id, "record_version": 1}
            except IntegrityError:
                continue
        raise ToolFailure("failed: could not allocate a record id")

    def update(
        self, system: str, record_id: str, claims: Claims, changes: Mapping[str, Any]
    ) -> dict[str, Any]:
        current = self.get(system, claims.usecase_id, record_id)
        if current is None:
            raise ToolFailure(f"not found: {record_id}")
        version = int(current["record_version"]) + 1
        meta = ("id", "record_version", "kind", "at", "terminal")
        body = {k: v for k, v in current.items() if k not in meta}
        body.update(changes)
        try:
            with self.engine.begin() as conn:
                self._insert(conn, system, str(current["kind"]), record_id, version, claims, body)
        except IntegrityError:
            raise ToolFailure(f"refused: {record_id} changed; read again") from None
        return {**body, "id": record_id, "record_version": version}

    def _insert(
        self,
        conn: Any,
        system: str,
        kind: str,
        record_id: str,
        version: int,
        claims: Claims,
        body: Mapping[str, Any],
    ) -> None:
        conn.execute(
            text(
                "INSERT INTO tools.enterprise_record (system, kind, record_id, version, "
                "usecase_id, run_id, terminal_id, body, at) VALUES (:s, :k, :r, :v, :u, :run, "
                ":t, :b, now())"
            ).bindparams(bindparam("b", type_=JSONB)),
            {
                "s": system,
                "k": kind,
                "r": record_id,
                "v": version,
                "u": claims.usecase_id,
                "run": claims.run_id,
                "t": claims.terminal_id,
                "b": dict(body),
            },
        )

    def records(
        self, system: str, usecase_id: str, kind: str | None = None, record_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT ON (record_id) record_id, version, kind, body, at, "
                    "terminal_id FROM tools.enterprise_record "
                    "WHERE system = :s AND usecase_id = :u "
                    "AND (CAST(:k AS text) IS NULL OR kind = :k) "
                    "AND (CAST(:r AS text) IS NULL OR record_id = :r) "
                    "ORDER BY record_id, version DESC"
                ),
                {"s": system, "u": usecase_id, "k": kind, "r": record_id},
            ).mappings()
            found = [
                {
                    **dict(r["body"]),
                    "id": r["record_id"],
                    "record_version": r["version"],
                    "kind": r["kind"],
                    "at": r["at"].isoformat(),
                    "terminal": r["terminal_id"],
                }
                for r in rows
            ]
        return sorted(found, key=lambda r: (r["id"].split("-")[0], int(r["id"].split("-")[1])))

    def get(self, system: str, usecase_id: str, record_id: str) -> dict[str, Any] | None:
        found = self.records(system, usecase_id, record_id=record_id)
        return found[0] if found else None

    def evidence(self, usecase_id: str, kind: str | None) -> list[dict[str, Any]]:
        kinds = [kind] if kind else list(EVIDENCE_KINDS)
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT tool_result_id, terminal_id, kind, package_hash, result, "
                    "result_sha256, at FROM tools.tool_result WHERE usecase_id = :u "
                    "AND kind = ANY(:k) ORDER BY tool_result_id"
                ),
                {"u": usecase_id, "k": kinds},
            ).mappings()
            return [
                {
                    "result_id": f"RES-{r['tool_result_id']}",
                    "terminal": r["terminal_id"],
                    "kind": r["kind"],
                    "package_hash": r["package_hash"],
                    "result_sha256": r["result_sha256"],
                    "at": r["at"].isoformat(),
                    "summary": {
                        k: v for k, v in dict(r["result"]).items() if k not in SUMMARY_DROP
                    },
                }
                for r in rows
            ]


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
