"""022 T010 (contracts/web-server.md): the ui process serves the built application and forwards
``/api`` to the platform API, with header allowlists, a strict CSP and no CORS.

The platform API is a stub behind ``httpx.MockTransport``; the built application is a temporary
folder.
"""

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from adlc.config.settings import UiSettings
from adlc.web.server import CSP, create_app

Handler = Callable[[httpx.Request], httpx.Response]


class StubApi:
    """Records what reached the platform API and answers with ``reply``."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.reply: Handler = lambda request: httpx.Response(200, json={"ok": True})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.seen.append(request)
        return self.reply(request)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<!doctype html><title>ADLC</title>")
    (folder / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside the build")
    return folder


@pytest.fixture
def stub() -> StubApi:
    return StubApi()


def client_for(dist: Path, stub: StubApi, **settings: object) -> TestClient:
    values: dict[str, object] = {
        "api_url": "http://api.test:8000",
        "ui_dist_dir": dist,
        "ui_dashboard_refresh": "7s",
        "env": "demo",
    }
    values.update(settings)
    app = create_app(UiSettings.model_validate(values), transport=httpx.MockTransport(stub))
    return TestClient(app, base_url="http://ui.test")


@pytest.fixture
def ui(dist: Path, stub: StubApi) -> Iterator[TestClient]:
    with client_for(dist, stub) as client:
        yield client


# ------------------------------------------------------------------------------ proxy


def test_forwards_method_path_query_and_body(ui: TestClient, stub: StubApi) -> None:
    answer = ui.post("/api/runs/UC-0001/T1/run-1/decisions?x=1", json={"decision": "pass"})
    assert answer.status_code == 200 and answer.json() == {"ok": True}
    (seen,) = stub.seen
    assert seen.method == "POST"
    assert str(seen.url) == "http://api.test:8000/runs/UC-0001/T1/run-1/decisions?x=1"
    assert json.loads(seen.content) == {"decision": "pass"}


def test_request_headers_come_from_an_allowlist(ui: TestClient, stub: StubApi) -> None:
    ui.post(
        "/api/usecases",
        json={},
        headers={
            "Cookie": "adlc_session=tok",
            "X-ADLC-CSRF": "abc",
            "Authorization": "Bearer other",
            "X-Foo": "bar",
        },
    )
    (seen,) = stub.seen
    assert seen.headers["cookie"] == "adlc_session=tok"
    assert seen.headers["x-adlc-csrf"] == "abc"
    assert seen.headers["content-type"] == "application/json"
    assert seen.headers["x-forwarded-proto"] == "http"
    assert seen.headers["x-forwarded-host"] == "ui.test"
    assert "authorization" not in seen.headers
    assert "x-foo" not in seen.headers


def test_answer_headers_come_from_an_allowlist(ui: TestClient, stub: StubApi) -> None:
    stub.reply = lambda request: httpx.Response(
        200,
        content=b"bytes",
        headers={
            "content-type": "application/octet-stream",
            "content-disposition": "attachment; filename*=UTF-8''notes.md",
            "set-cookie": "adlc_session=tok; HttpOnly; SameSite=Strict; Path=/",
            "x-internal": "secret",
            "server": "uvicorn",
        },
    )
    answer = ui.get("/api/runs/UC-0001/T1/run-1/attachments/abc")
    assert answer.content == b"bytes"
    assert answer.headers["content-disposition"].startswith("attachment")
    assert "HttpOnly" in answer.headers["set-cookie"]
    assert "x-internal" not in answer.headers
    assert answer.headers.get("server") != "uvicorn"


def test_status_and_error_shape_pass_through(ui: TestClient, stub: StubApi) -> None:
    stub.reply = lambda request: httpx.Response(409, json={"kind": "stale", "detail": "changed"})
    answer = ui.put("/api/runs/UC-0001/T1/run-1/artifacts/kpis", json={})
    assert answer.status_code == 409 and answer.json()["kind"] == "stale"


def test_an_upload_reaches_the_api_whole(ui: TestClient, stub: StubApi) -> None:
    data = b"x" * 300_000
    ui.post(
        "/api/runs/UC-0001/T1/run-1/artifacts/kpis/attachments",
        files={"file": ("notes.bin", data, "application/octet-stream")},
        data={"expected_version": "3"},
    )
    (seen,) = stub.seen
    assert seen.headers["content-type"].startswith("multipart/form-data")
    assert data in seen.content and b'name="expected_version"' in seen.content


def test_api_unreachable_answers_in_the_platform_error_shape(ui: TestClient, stub: StubApi) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    stub.reply = down
    answer = ui.get("/api/inbox")
    assert answer.status_code == 502
    assert answer.json() == {"kind": "unavailable", "detail": "the platform could not be reached"}


# ------------------------------------------------------------------------------ the built application


def test_client_side_routes_get_the_page(ui: TestClient) -> None:
    for path in ("/", "/inbox", "/run", "/usecases/new"):
        answer = ui.get(path, params={"run": "UC-0001/T1/run-1"})
        assert answer.status_code == 200, path
        assert answer.text.startswith("<!doctype html>")
        assert answer.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_and_missing_ones_are_not_found(ui: TestClient) -> None:
    answer = ui.get("/assets/index-abc123.js")
    assert answer.status_code == 200 and "console.log" in answer.text
    assert answer.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert ui.get("/assets/missing.js").status_code == 404


def test_nothing_outside_the_build_is_served(ui: TestClient) -> None:
    for path in ("/assets/../../secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt", "/../secret.txt"):
        answer = ui.get(path)
        assert "outside the build" not in answer.text, path


def test_only_get_outside_the_api(ui: TestClient) -> None:
    assert ui.post("/inbox").status_code == 405


# ------------------------------------------------------------------------------ settings and health


def test_runtime_settings_for_the_page(ui: TestClient) -> None:
    answer = ui.get("/config.json")
    assert answer.json() == {"env": "demo", "dashboard_refresh_seconds": 7}
    assert answer.headers["cache-control"] == "no-store"


def test_health_reports_a_missing_build(tmp_path: Path, stub: StubApi) -> None:
    with client_for(tmp_path / "nowhere", stub) as client:
        answer = client.get("/health")
    assert answer.status_code == 503 and answer.json() == {"status": "missing build"}


def test_health_ok(ui: TestClient) -> None:
    answer = ui.get("/health")
    assert answer.status_code == 200 and answer.json() == {"status": "ok"}


# ------------------------------------------------------------------------------ headers and logs


def test_security_headers_on_every_answer(ui: TestClient, stub: StubApi) -> None:
    for answer in (
        ui.get("/inbox"),
        ui.get("/assets/index-abc123.js"),
        ui.get("/assets/missing.js"),
        ui.get("/config.json"),
        ui.get("/api/inbox"),
    ):
        assert answer.headers["content-security-policy"] == CSP
        assert answer.headers["x-content-type-options"] == "nosniff"
        assert answer.headers["referrer-policy"] == "same-origin"
        assert answer.headers["cross-origin-opener-policy"] == "same-origin"


def test_csp_is_strict_for_scripts() -> None:
    assert "script-src 'self';" in CSP and "unsafe-eval" not in CSP
    assert "frame-ancestors 'none'" in CSP and "object-src 'none'" in CSP


def test_no_cors(ui: TestClient, stub: StubApi) -> None:
    stub.reply = lambda request: httpx.Response(
        200, json={}, headers={"access-control-allow-origin": "*"}
    )
    for answer in (
        ui.get("/api/inbox", headers={"Origin": "http://evil.test"}),
        ui.options("/api/usecases", headers={"Origin": "http://evil.test"}),
        ui.get("/inbox", headers={"Origin": "http://evil.test"}),
    ):
        assert not any(h.startswith("access-control-") for h in answer.headers)


def test_logs_hold_no_headers_query_or_bodies(
    ui: TestClient, stub: StubApi, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="adlc.web"):
        ui.post(
            "/api/usecases?token=q-secret",
            json={"intake_text": "body-secret"},
            headers={"Cookie": "adlc_session=cookie-secret", "X-ADLC-CSRF": "csrf-secret"},
        )
    logged = caplog.text
    assert "/api/usecases" in logged and "200" in logged
    for secret in ("q-secret", "body-secret", "cookie-secret", "csrf-secret"):
        assert secret not in logged
