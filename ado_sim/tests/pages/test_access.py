"""017 T017: every page needs a session; every page POST needs CSRF; the API is unchanged
(FR-001, FR-004, SC-004)."""

from __future__ import annotations

import re

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.pages.conftest import sign_in

SAMPLE = {"organization": "adlc-demo", "project": "Agentic%20ADLC", "item_id": "1"}


def _all_routes(routes: list[object]) -> list[object]:
    """Routes, including those of routers FastAPI keeps nested (``original_router``)."""
    found: list[object] = []
    for route in routes:
        nested = getattr(route, "original_router", None)
        found += _all_routes(list(nested.routes)) if nested is not None else [route]
    return found


def _page_routes(client: TestClient) -> list[tuple[str, str]]:
    found = []
    for route in _all_routes(list(client.app.routes)):  # type: ignore[attr-defined]
        if (
            isinstance(route, APIRoute)
            and not route.include_in_schema
            and route.path not in ("/_signin",)
        ):
            path = re.sub(r"\{(\w+)\}", lambda m: SAMPLE[m.group(1)], route.path)
            found += [(method, path) for method in route.methods or ()]
    return found


def test_every_page_route_needs_a_session(client: TestClient) -> None:
    routes = _page_routes(client)
    assert len(routes) >= 6
    for method, path in routes:
        answer = client.request(method, path)
        assert answer.status_code == 303 and answer.headers["location"].startswith("/_signin"), (
            method,
            path,
        )
        htmx = client.request(method, path, headers={"HX-Request": "true"})
        assert htmx.status_code == 200 and htmx.headers["HX-Redirect"] == "/_signin", (method, path)


def test_every_page_post_needs_csrf(client: TestClient) -> None:
    sign_in(client)
    for method, path in _page_routes(client):
        if method == "POST":
            assert client.post(path, data={"title": "x", "csrf": "wrong"}).status_code == 403, path


def test_the_api_still_answers_401_without_a_token(client: TestClient) -> None:
    sign_in(client)  # a page session is not an API credential
    answer = client.get(
        "/adlc-demo/Agentic%20ADLC/_apis/wit/workitems/1", params={"api-version": "7.1"}
    )
    assert answer.status_code == 401


def test_security_headers(client: TestClient) -> None:
    sign_in(client)
    page = client.get("/adlc-demo/Agentic%20ADLC/_boards/board")
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["cache-control"] == "no-store"
    static = client.get("/_static/board.css")
    assert static.status_code == 200 and "max-age" in static.headers["cache-control"]


def test_an_unknown_page_is_an_html_404(client: TestClient) -> None:
    sign_in(client)
    answer = client.get("/adlc-demo/Agentic%20ADLC/_nothing")
    assert answer.status_code == 404 and "text/html" in answer.headers["content-type"]
