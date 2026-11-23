"""The API reference (docs/api-reference.md) is generated from the API itself and kept current.

It fails when an operation, its contract (adlc.api.docs), a request model or an answer model
changed without `make api-docs`.
"""

from scripts.api_docs import DOCUMENT, render
from scripts.export_openapi import openapi_document


def test_committed_reference_matches_the_api() -> None:
    assert DOCUMENT.exists(), "docs/api-reference.md is missing: run `make api-docs`"
    assert DOCUMENT.read_text() == render(openapi_document()), (
        "docs/api-reference.md is stale: run `make api-docs`"
    )


def test_every_operation_is_in_the_reference() -> None:
    document = openapi_document()
    text = render(document)
    for path, operations in document["paths"].items():
        for method in operations:
            assert f"### `{method.upper()} {path}`" in text
