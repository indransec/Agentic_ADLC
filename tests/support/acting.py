"""Harness for the acting agents (feature 011): the named terminal agents run as the registered
model agents with scripted replies; their tools go through the real gate, run tokens and records to
the pilot bridge over the fake pilot, and to the tools server on the harness's database."""

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from adlc.agents.catalogue import load_catalogues
from adlc.agents.replay import AgentReplies, Planned, replay_gateway
from adlc.agents.store import SqlCallRecorder
from adlc.config.settings import BridgeSettings, ToolsSettings
from adlc.spec_toolkit.registry import InMemorySpecRegistry
from adlc.tools.bridge.app import build_bridge
from adlc.tools.client import McpClient
from adlc.tools.enterprise.app import build_tools
from tests.support.fake_pilot import FakePilot, urls
from tests.support.grounded import BUNDLE, prompt_bodies
from tests.support.orchestration import Harness, harness
from tests.support.pg import REPO_ROOT, PlatformDatabase
from tests.support.tools import ALLOWED, KEY, serve

SPECS = REPO_ROOT / "adlc-specs"
HASH = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass
class Acting:
    h: Harness
    pilot: FakePilot
    replies: AgentReplies


def last_tool_output(messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """The JSON of the latest tool result in the conversation (inside its data block)."""
    for message in reversed(messages):
        content = message["content"]
        if "<data" in content and message["role"] == "user":
            body = content[content.index(">") + 1 : content.rindex("</data>")].strip()
            try:
                found: dict[str, Any] = json.loads(body)
                return found
            except json.JSONDecodeError:
                continue
    return {}


def tool(name: str, arguments: Mapping[str, Any] | None = None) -> str:
    return json.dumps({"tool": {"name": name, "arguments": dict(arguments or {})}})


@contextmanager
def acting(
    db: PlatformDatabase,
    replies: Mapping[str, Sequence[Planned]],
    agents: tuple[str, ...],
    work: Path,
    pilot: FakePilot | None = None,
) -> Iterator[Acting]:
    pilot = pilot or FakePilot()
    scripted = AgentReplies(prompt_bodies(), replies)
    models = load_catalogues(InMemorySpecRegistry.from_bundle(BUNDLE), "default")[0]

    class Late:
        gateway: Any = None

        def complete(self, request: Any) -> Any:
            return self.gateway.complete(request)

    late = Late()
    with ExitStack() as stack:
        pilot_url = stack.enter_context(serve(pilot.app()))
        u = urls(pilot_url)
        bridge = BridgeSettings(
            tools_token_key=SecretStr(KEY),
            bridge_allowed_hosts=",".join(ALLOWED),
            bridge_data_dir=work / "bridge",
            bridge_pilot_dev_url=u.dev,
            bridge_pilot_test_url=u.test,
            bridge_pilot_prodsim_url=u.prodsim,
            bridge_pilot_lab_url=u.lab,
            bridge_pilot_traffic_url=u.traffic,
            bridge_jaeger_url=f"{pilot_url}/jaeger",
            spec_dir=SPECS,
            redteam_suite=REPO_ROOT / "data" / "redteam" / "suite.yaml",
        )
        bridge_url = stack.enter_context(serve(build_bridge(bridge)))
        client = McpClient({"bridge": bridge_url}, 60)
        h = stack.enter_context(
            harness(db, gateway=late, model_agents=agents, tools_client=client, tools_token_key=KEY)
        )
        tools = ToolsSettings(
            env="dev",
            db_host="unused",
            db_app_password=SecretStr("unused-password-0001"),
            tools_token_key=SecretStr(KEY),
            tools_allowed_hosts=",".join(ALLOWED),
            spec_dir=SPECS,
            controls_file=REPO_ROOT / "data" / "controls" / "controls.yaml",
        )
        client.urls["tools"] = stack.enter_context(serve(build_tools(tools, h.app)))
        late.gateway = replay_gateway(models, scripted, SqlCallRecorder(h.app))
        yield Acting(h, pilot, scripted)
