"""T009: the knowledge MCP server through the real MCP client (contracts/knowledge-mcp.md)."""

from collections.abc import Iterator

import httpx
import pytest
from pydantic import ValidationError

from adlc.config.settings import KnowledgeSettings
from tests.support.knowledge import FIXTURES, call, knowledge_server

STRATEGY = ["/strategy, /policies"]


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    with knowledge_server() as url:
        yield url


def test_health_needs_no_token(base: str) -> None:
    body = httpx.get(f"{base}/health").json()
    assert body["status"] == "ok" and body["documents"] >= 10
    assert set(body["sources"]) == {
        "arch_repo",
        "confluence",
        "jira",
        "mcp_registry",
        "portfolio",
        "sharepoint",
    }


def test_mcp_needs_the_token(base: str) -> None:
    assert httpx.post(f"{base}/mcp/sharepoint/", json={}).status_code == 401
    with pytest.raises(Exception):  # noqa: B017 - the client fails on the 401
        call(base, "sharepoint", "search", {"query": "claims"}, token="wrong-token-123456")


def test_search_in_scope_and_class(base: str) -> None:
    error, found = call(
        base,
        "sharepoint",
        "search",
        {"query": "claims data owner", "scope": STRATEGY, "max_class": "internal"},
    )
    assert not error
    docs = [r["document"] for r in found["results"]]
    assert docs and docs[0] == "policies/data-classification.md"
    assert "policies/board-only.md" not in docs  # confidential, above internal
    first = found["results"][0]
    assert first["section"] == "Claims data" and first["content_hash"].startswith("sha256:")
    assert first["synthetic"] is True


def test_nothing_outside_scope_or_without_a_class(base: str) -> None:
    error, found = call(base, "sharepoint", "search", {"query": "claims", "max_class": "internal"})
    assert not error and found["results"] == []  # no scope sent: nothing in scope
    error, found = call(
        base, "sharepoint", "search", {"query": "claims", "scope": STRATEGY, "max_class": "nope"}
    )
    assert not error and found["results"] == []  # unknown class fails closed


def test_collection_labels(base: str) -> None:
    error, found = call(
        base,
        "arch_repo",
        "search",
        {
            "query": "agent approval",
            "scope": ["reference architectures, ADRs"],
            "max_class": "internal",
        },
    )
    assert not error and found["results"][0]["document"] == "ra-claims.md"


def test_read_and_errors(base: str) -> None:
    args = {"scope": STRATEGY, "max_class": "internal"}
    error, page = call(
        base,
        "sharepoint",
        "read",
        {"document": "policies/data-classification.md", "section": "Claims data", **args},
    )
    assert not error and "claims operations lead" in page["text"] and page["cut"] is False
    error, outline = call(
        base, "sharepoint", "read", {"document": "policies/data-classification.md", **args}
    )
    assert not error and "Claims data" in outline["text"]
    error, text = call(base, "sharepoint", "read", {"document": "policies/board-only.md", **args})
    assert error and "out of scope" in text
    error, text = call(base, "sharepoint", "read", {"document": "nope.md", **args})
    assert error and "not found" in text
    error, text = call(base, "sharepoint", "search", {"query": "", **args})
    assert error and "invalid arguments" in text


def test_refuses_to_start_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADLC_KNOWLEDGE_DIR", str(FIXTURES))
    monkeypatch.delenv("ADLC_KNOWLEDGE_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        KnowledgeSettings()  # type: ignore[call-arg]
