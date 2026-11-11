"""Harness with the real T0-T2 agents (feature 008): scripted replies per agent through the
production gateway rules, and the knowledge MCP server over a document folder."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adlc.agents.catalogue import load_catalogues
from adlc.agents.knowledge import KnowledgeCaller, McpCaller
from adlc.agents.prompts import BundleSpecTexts
from adlc.agents.replay import AgentReplies, Planned, replay_gateway
from adlc.agents.store import SqlCallRecorder
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry
from tests.support.knowledge import TOKEN, knowledge_server
from tests.support.orchestration import SPECS, Harness, harness
from tests.support.pg import REPO_ROOT, PlatformDatabase

KNOWLEDGE = REPO_ROOT / "data" / "knowledge"
BUNDLE = load_bundle(SPECS)
TEXTS = BundleSpecTexts(BUNDLE)


def prompt_bodies() -> dict[str, str]:
    agents = BUNDLE.catalogue_data("agents")["agents"]
    return {
        a["id"]: TEXTS.prompt(a["prompt"]["id"], a["prompt"]["version"]).body
        for a in agents
        if a.get("prompt")
    }


@dataclass
class Grounded:
    h: Harness
    replies: AgentReplies
    knowledge_url: str
    calls: list[tuple[str, str]]  # (source, tool) of every call that reached the caller


class Spy:
    """Records every knowledge call that gets past the tool gate, then delegates."""

    def __init__(self, inner: KnowledgeCaller) -> None:
        self.inner = inner
        self.calls: list[tuple[str, str]] = []

    def __call__(self, source: str, tool: str, arguments: Mapping[str, Any]) -> tuple[bool, Any]:
        self.calls.append((source, tool))
        return self.inner(source, tool, arguments)


@contextmanager
def grounded(
    db: PlatformDatabase,
    replies: Mapping[str, Sequence[Planned]],
    folder: Path = KNOWLEDGE,
    caller: KnowledgeCaller | None = None,
    **kwargs: Any,
) -> Iterator[Grounded]:
    scripted = AgentReplies(prompt_bodies(), replies)
    models = load_catalogues(InMemorySpecRegistry.from_bundle(BUNDLE), "default")[0]

    class Late:
        gateway: Any = None

        def complete(self, request: Any) -> Any:
            return self.gateway.complete(request)

    late = Late()
    with knowledge_server(folder) as url:
        spy = Spy(caller or McpCaller(url, TOKEN))
        with harness(db, gateway=late, real_agents=True, knowledge_caller=spy, **kwargs) as h:
            late.gateway = replay_gateway(models, scripted, SqlCallRecorder(h.app))
            yield Grounded(h, scripted, url, spy.calls)
