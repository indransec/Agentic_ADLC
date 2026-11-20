"""The published contract equals what the app serves, and nothing else is served (T042, FR-020)."""

from __future__ import annotations

import json

import pytest
from fastapi.routing import APIRoute

from ado_sim.app import build_app
from tests.conftest import PROJECT_DIR, WIT, ApiClient

OPENAPI = PROJECT_DIR / "contract" / "openapi.json"


def test_served_document_equals_the_committed_file(api: ApiClient) -> None:
    response = api.http.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == json.loads(OPENAPI.read_text(encoding="utf-8"))


def test_documented_paths_equal_the_routes() -> None:
    documented = {
        (method.upper(), path)
        for path, operations in json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"].items()
        for method in operations
    }
    routes = {
        (method, route.path)
        for route in build_app().routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert documented == routes


def test_every_ado_operation_requires_api_version() -> None:
    paths = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    for path, operations in paths.items():
        if "/_apis/" not in path:
            continue
        for operation in operations.values():
            versions = [p for p in operation["parameters"] if p["name"] == "api-version"]
            assert versions and versions[0]["required"], path


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{WIT}/reporting/workitemrevisions"),
        ("DELETE", f"{WIT}/workitems/1"),
        ("PUT", f"{WIT}/workitems/1"),
        ("GET", f"{WIT}/queries"),
        ("GET", "/adlc-demo/Agentic%20ADLC/_apis/git/repositories"),
        ("POST", f"{WIT}/workitems/1/comments/1/reactions/like"),
    ],
)
def test_anything_else_under_apis_is_404(api: ApiClient, method: str, path: str) -> None:
    response = api.call(method, path)
    assert response.status_code == 404
    assert response.json()["typeKey"] == "ResourceNotFoundException"
