"""022 T009 (FR-021, N-09): the committed OpenAPI document is the API's own.

The web application's types are generated from ``web/src/api/openapi.json``; if the API's answers
change and the document is not regenerated, this fails. The web side checks its generated types
against the same document (``make web-typecheck``).
"""

from scripts.export_openapi import DOCUMENT, openapi_document, render


def test_committed_document_matches_the_api() -> None:
    assert DOCUMENT.exists(), "web/src/api/openapi.json is missing: run `make openapi`"
    assert DOCUMENT.read_text() == render(openapi_document()), (
        "web/src/api/openapi.json is stale: run `make openapi`"
    )


def test_every_platform_answer_is_described() -> None:
    """FR-020: every JSON answer is a named model or a list of one; none is an open object."""
    loose = []
    for path, methods in openapi_document()["paths"].items():
        for method, operation in methods.items():
            for status, response in operation.get("responses", {}).items():
                if not status.startswith("2"):
                    continue
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if schema is None:
                    continue  # raw answers (download) and 204s
                named = "$ref" in schema or "$ref" in schema.get("items", {})
                if not named:
                    loose.append(f"{method.upper()} {path} {status}")
    assert loose == [], loose
