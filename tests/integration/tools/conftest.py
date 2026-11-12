"""Fixtures for the feature 010 tool tests: a fake pilot, the bridge served over it, the pinned
terminal specs from the repository, and a tool gate with the real authorisation rules."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from ruamel.yaml import YAML
from sqlalchemy import Engine, text

from adlc.agents.catalogue import AgentDefinition, ToolBinding
from adlc.agents.mcp_tools import BoundValues, McpTool
from adlc.agents.tool_records import SqlToolRecords
from adlc.agents.tools import ToolGate, ToolOutput, ToolRefused
from adlc.config.settings import BridgeSettings, ToolsSettings
from adlc.orchestration.interfaces import EvalContext
from adlc.policy import authorization
from adlc.policy.evidence import Answer, Evidence
from adlc.policy.values import NOT_AVAILABLE
from adlc.tools.bridge.app import build_bridge
from adlc.tools.catalogue import CATALOGUE
from adlc.tools.client import McpClient
from adlc.tools.enterprise.app import build_tools
from adlc.tools.registry import Registry
from tests.support.fake_pilot import FakePilot, urls
from tests.support.pg import REPO_ROOT
from tests.support.tools import ALLOWED, KEY, serve

SPECS = REPO_ROOT / "adlc-specs"


def pinned(terminal: str) -> dict[str, Any]:
    return dict(YAML(typ="safe").load((SPECS / "terminals" / f"{terminal}.yaml").read_text()))


class SpecPolicy:
    """The real authorisation rules (feature 004 ``decide``) over the repository's pinned specs."""

    def __init__(self, specs: Mapping[str, Mapping[str, Any]]) -> None:
        self.specs = specs

    def authorize_decision(
        self, actor: str, action: str, resource: str, context: EvalContext
    ) -> tuple[bool, str]:
        return authorization.decide(
            actor, action, resource, context.run_id, self.specs.get(context.terminal_id)
        )

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool:
        return self.authorize_decision(actor, action, resource, context)[0]


@dataclass
class FakeEvidence:
    records: dict[str, Any] = field(default_factory=dict)

    def get(self, source: str, context: EvalContext) -> Answer:
        return Evidence(self.records[source], source) if source in self.records else NOT_AVAILABLE


@dataclass
class Tools:
    pilot: FakePilot
    pilot_url: str
    bridge_url: str
    engine: Engine
    evidence: FakeEvidence
    bridge_dir: Path
    tools_url: str = ""

    def gate(self, terminal: str, *tools: str) -> Callable[..., ToolOutput | ToolRefused]:
        spec = pinned(terminal)
        bindings = []
        for name in tools:
            tool = CATALOGUE.tools[name]
            scope = tool.scope
            if scope.startswith("{"):
                scopes = spec["terminal"]["authorities"]["tool_scopes"]
                scope = next(
                    s.split(":")[2]
                    for s in scopes
                    if s.startswith(f"mcp:{tool.server}:") and s.split(":")[2] in ("dev", "test")
                )
            bindings.append(ToolBinding(name, f"mcp:{tool.server}:{scope}"))
        agent = AgentDefinition(
            f"{terminal.lower()}-agent", "1.0.0", "model", "coding", None, tuple(bindings)
        )
        registry = Registry.load(SPECS)
        client = McpClient({"bridge": self.bridge_url, "tools": self.tools_url}, 30)
        bound = BoundValues(self.evidence, registry.bound_values)
        records = SqlToolRecords(self.engine, _Clock())
        gate = ToolGate(
            SpecPolicy({terminal: spec}),  # type: ignore[arg-type]
            {
                n: McpTool(
                    CATALOGUE.tools[n],
                    str(registry.host_of(CATALOGUE.tools[n].server)),
                    client,
                    KEY,
                    bound,
                    records,
                )
                for n in tools
            },
        )
        run_id = f"UC-0001/{terminal}/run-1"

        def call(
            name: str, arguments: Mapping[str, Any] | None = None, *, as_run: str | None = None
        ) -> ToolOutput | ToolRefused:
            return gate.call(
                run_id=run_id,
                usecase_id="UC-0001",
                terminal_id=terminal,
                agent=agent,
                name=name,
                arguments=arguments or {},
                on_behalf_of=as_run,
                spec=spec,
            )

        return call

    def calls(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT tool, scope, outcome, reason FROM tools.tool_call ORDER BY tool_call_id"
                )
            ).mappings()
            return [dict(r) for r in rows]

    def results(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT kind, package_hash, result FROM tools.tool_result ORDER BY tool_result_id"
                )
            ).mappings()
            return [dict(r) for r in rows]


class _Clock:
    def now(self) -> Any:
        from datetime import UTC, datetime

        return datetime.now(UTC)


def bridge_settings(pilot_url: str, data_dir: Path) -> BridgeSettings:
    u = urls(pilot_url)
    return BridgeSettings(
        tools_token_key=SecretStr(KEY),
        bridge_allowed_hosts=",".join(ALLOWED),
        bridge_data_dir=data_dir,
        bridge_pilot_dev_url=u.dev,
        bridge_pilot_test_url=u.test,
        bridge_pilot_prodsim_url=u.prodsim,
        bridge_pilot_lab_url=u.lab,
        bridge_pilot_traffic_url=u.traffic,
        bridge_jaeger_url=f"{pilot_url}/jaeger",
        bridge_monitor_interval_s=0.2,
        spec_dir=SPECS,
        redteam_suite=REPO_ROOT / "data" / "redteam" / "suite.yaml",
    )


@pytest.fixture
def tools(app_engine: Engine, tmp_path: Path) -> Iterator[Tools]:
    pilot = FakePilot()
    with serve(pilot.app()) as pilot_url:
        settings = bridge_settings(pilot_url, tmp_path / "bridge")
        enterprise = ToolsSettings(
            env="dev",
            db_host="unused",
            db_app_password=SecretStr("unused-password-0001"),
            tools_token_key=SecretStr(KEY),
            tools_allowed_hosts=",".join(ALLOWED),
            spec_dir=SPECS,
            controls_file=REPO_ROOT / "data" / "controls" / "controls.yaml",
        )
        with (
            serve(build_bridge(settings)) as bridge_url,
            serve(build_tools(enterprise, app_engine)) as tools_url,
        ):
            yield Tools(
                pilot,
                pilot_url,
                bridge_url,
                app_engine,
                FakeEvidence(),
                tmp_path / "bridge",
                tools_url,
            )
