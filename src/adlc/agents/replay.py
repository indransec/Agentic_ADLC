"""``adlc-replay`` (feature 008, task T029) and the replay transport it shares with the tests.

``AgentReplies`` answers model calls per agent, in call order: the agent is recognised by its
registered system prompt, so a recording made live replays without a provider, whatever model
the catalogue lists. Nothing here names a terminal, an agent or a model.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

import typer

from adlc.agents.catalogue import ModelCatalogue
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import CallRecorder, ProviderReply

Planned = str | ProviderReply | Callable[[Sequence[Mapping[str, str]]], str | ProviderReply]
SIGNATURE = 300  # characters of a system prompt that identify its agent

app = typer.Typer(help="Replay the reference use cases through the grounded terminals.")


class AgentReplies:
    """Scripted or recorded replies per agent id; ``prompts`` maps agent ids to prompt bodies."""

    def __init__(
        self, prompts: Mapping[str, str], replies: Mapping[str, Sequence[Planned]]
    ) -> None:
        self.signatures = {aid: body.strip()[:SIGNATURE] for aid, body in prompts.items()}
        self.replies = {aid: list(r) for aid, r in replies.items()}
        self.used: dict[str, int] = defaultdict(int)
        self.calls: list[tuple[str, int]] = []

    def agent_of(self, messages: Sequence[Mapping[str, str]]) -> str | None:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        return next((aid for aid, sig in self.signatures.items() if system.startswith(sig)), None)

    def __call__(self, messages: Sequence[Mapping[str, str]]) -> ProviderReply:
        agent = self.agent_of(messages)
        planned = self.replies.get(agent or "") or []
        n = self.used[agent or ""]
        self.used[agent or ""] = n + 1
        self.calls.append((agent or "?", n))
        if n >= len(planned):
            return reply("", outcome="request_error", reason=f"no reply {n + 1} for {agent}")
        item = planned[n]
        answer = item(messages) if callable(item) else item
        return answer if isinstance(answer, ProviderReply) else reply(answer, tokens=(400, 200))


def replay_gateway(
    catalogue: ModelCatalogue, replies: AgentReplies, recorder: CallRecorder | None = None
) -> FakeGateway:
    """The production gateway rules over ``replies``, whichever catalogue model is tried."""
    models = {e.model for entries in catalogue.tiers.values() for e in entries}
    return FakeGateway(catalogue, dict.fromkeys(models, replies), recorder=recorder)


@app.command()
def run() -> None:
    """Placeholder until task T029."""
    raise typer.Exit(2)


__all__ = ["AgentReplies", "Planned", "app", "replay_gateway"]
