"""SC-007 and FR-024: tokens and field values never leak (T048).

Tokens are issued with the operator command, every contract fixture is replayed with them, and
values carrying marker strings are sent in accepted and refused requests. Afterwards no token
appears in any response body or header, captured log line, the seed file, any fixture or the
data file (which holds only hashes), and no marker appears in any log line.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ado_sim import auth
from ado_sim.app import create_app
from ado_sim.cli import OK, run
from ado_sim.db import Database
from ado_sim.settings import load_settings
from tests.conftest import KEY, SEED, SERVICE, WIT
from tests.contract.test_fixtures import FILES

FIELD_MARKER = "MARKER-FIELD-7f3a"
COMMENT_MARKER = "MARKER-COMMENT-91c2"
REFUSED_MARKER = "MARKER-REFUSED-5d08"


def _issue(names: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    tokens = {}
    for name in names:
        capsys.readouterr()
        assert run(["token", "issue", name, "--label", "scan"]) == OK
        tokens[name] = capsys.readouterr().out.strip().splitlines()[-1]
    return tokens


def test_no_token_or_value_leaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    data = tmp_path / "sim.db"
    monkeypatch.setenv("ADO_SIM_DB_PATH", str(data))
    monkeypatch.setenv("ADO_SIM_TOKEN_KEY", KEY)
    monkeypatch.setenv("ADO_SIM_SEED_FILE", str(SEED))
    assert run(["migrate"]) == OK
    assert run(["seed", "--file", str(SEED)]) == OK
    tokens = _issue([SERVICE, "product.owner@adlc.demo"], capsys)
    assert all(len(token) >= 40 for token in tokens.values())
    caplog.set_level(logging.DEBUG)

    seen: list[str] = []

    def record(response: Any) -> Any:
        seen.append(response.text)
        seen.extend(f"{k}: {v}" for k, v in response.headers.items())
        return response

    with TestClient(create_app(load_settings())) as client:
        bearer = {"Authorization": f"Bearer {tokens[SERVICE]}"}
        basic_value = base64.b64encode(f":{tokens[SERVICE]}".encode()).decode()
        basic = {"Authorization": f"Basic {basic_value}"}
        for number, path in enumerate(FILES):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            for request in [*fixture["setup"], fixture["request"]]:
                headers = dict(request.get("headers", {}))
                if request.get("auth", True):
                    headers.update(basic if number % 2 else bearer)
                body = json.dumps(request["body"]) if "body" in request else None
                record(
                    client.request(
                        request["method"],
                        request["path"],
                        params=request["query"],
                        headers=headers,
                        content=body,
                    )
                )
        json_patch = {**bearer, "Content-Type": "application/json-patch+json"}
        item = record(
            client.post(
                f"{WIT}/workitems/$Task",
                params={"api-version": "7.1"},
                headers=json_patch,
                content=json.dumps(
                    [{"op": "add", "path": "/fields/System.Title", "value": FIELD_MARKER}]
                ),
            )
        ).json()
        assert FIELD_MARKER in json.dumps(item)
        record(
            client.post(
                f"{WIT}/workitems/{item['id']}/comments",
                params={"api-version": "7.1-preview.4"},
                headers=bearer,
                json={"text": COMMENT_MARKER},
            )
        )
        refusals = [
            client.patch(
                f"{WIT}/workitems/{item['id']}",
                params={"api-version": "7.1"},
                headers=json_patch,
                content=json.dumps(
                    [{"op": "add", "path": "/fields/Custom.Unknown", "value": REFUSED_MARKER}]
                ),
            ),
            client.post(
                f"{WIT}/wiql",
                params={"api-version": "7.1"},
                headers=bearer,
                json={
                    "query": "SELECT [System.Id] FROM workitems WHERE [System.Title]"
                    f" CONTAINS '{REFUSED_MARKER}'"
                },
            ),
            client.get(
                f"{WIT}/workitems/1",
                params={"api-version": "7.1"},
                headers={"Authorization": f"Bearer {tokens[SERVICE]}x"},
            ),
        ]
        assert [r.status_code for r in refusals] == [400, 400, 401]
        for response in refusals:
            record(response)

    logged = caplog.text + capsys.readouterr().err
    assert "request method=" in logged
    for marker in (FIELD_MARKER, COMMENT_MARKER, REFUSED_MARKER):
        assert marker not in logged, marker

    files = [SEED, *FILES]
    stored = b"".join(
        candidate.read_bytes()
        for candidate in (data, Path(f"{data}-wal"), Path(f"{data}-shm"))
        if candidate.exists()
    )
    for token in tokens.values():
        assert not any(token in text for text in seen)
        assert token not in logged
        assert not any(token in f.read_text(encoding="utf-8") for f in files)
        assert token.encode() not in stored
    db = Database(data)
    with db.read() as conn:
        hashes = {row[0] for row in conn.execute("SELECT token_hash FROM access_token")}
    db.close()
    assert {auth.hash_token(KEY, token) for token in tokens.values()} <= hashes
