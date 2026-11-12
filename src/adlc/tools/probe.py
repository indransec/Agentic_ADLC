"""``adlc-tools-probe`` (feature 010, quickstart §2): call any MCP tool as a named terminal for a
use case, through the same gate, run token, bound values and records an agent's call uses. A dev
and demo command, not a service; it refuses to run in any other environment.

The tool servers publish no ports, so run it inside the platform network, e.g.::

    docker compose -f deploy/compose.yaml --env-file .env run --rm orchestrator \\
        adlc-tools-probe --usecase <use case> --terminal <terminal id> <tool>
"""

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings

app = typer.Typer(help="Call an MCP tool as a terminal (dev and demo only).", add_completion=False)
ALLOWED_ENVS = ("dev", "demo")


def _value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@app.command()
def call(
    tool: Annotated[str, typer.Argument(help="the tool, e.g. ci_run or pilot_env_create")],
    usecase: Annotated[str, typer.Option(help="the use case id")],
    terminal: Annotated[str, typer.Option(help="the terminal whose scopes the call uses")],
    arg: Annotated[list[str] | None, typer.Option(help="key=value (JSON values allowed)")] = None,
    files: Annotated[Path | None, typer.Option(help="a folder whose files go in `files`")] = None,
    run: Annotated[
        str | None, typer.Option(help="the run id (default <usecase>/<terminal>/probe)")
    ] = None,
) -> None:
    # Imports here keep the module light for the console-script check.
    from adlc.agents.catalogue import AgentDefinition, ToolBinding  # noqa: PLC0415
    from adlc.agents.mcp_tools import BoundValues, McpTool, scope_for  # noqa: PLC0415
    from adlc.agents.tool_records import SqlToolRecords  # noqa: PLC0415
    from adlc.agents.tools import ToolGate, ToolOutput  # noqa: PLC0415
    from adlc.db.engine import app_engine  # noqa: PLC0415
    from adlc.orchestration.interfaces import EvalContext, SystemClock  # noqa: PLC0415
    from adlc.policy import authorization  # noqa: PLC0415
    from adlc.policy.evidence import SqlEvidenceProvider  # noqa: PLC0415
    from adlc.spec_toolkit.registry import SqlSpecRegistry  # noqa: PLC0415
    from adlc.tools.catalogue import CATALOGUE  # noqa: PLC0415
    from adlc.tools.client import McpClient  # noqa: PLC0415
    from adlc.tools.registry import Registry  # noqa: PLC0415

    settings = load_settings_or_exit(OrchestratorSettings)
    if settings.env not in ALLOWED_ENVS or settings.tools_token_key is None:
        print(
            "adlc: the probe runs only in dev or demo, with ADLC_TOOLS_TOKEN_KEY", file=sys.stderr
        )
        raise typer.Exit(2)
    spec_tool = CATALOGUE.get(tool)
    if spec_tool is None:
        print(f"adlc: unknown tool {tool}", file=sys.stderr)
        raise typer.Exit(2)
    engine = app_engine(settings)
    registry = SqlSpecRegistry(engine)
    entry = registry.entry(terminal)
    servers_entry = registry.catalogue("mcp_servers")
    if entry is None or servers_entry is None:
        print(f"adlc: no active spec for {terminal} or no MCP registry", file=sys.stderr)
        raise typer.Exit(2)
    spec = entry.spec
    servers = Registry.from_content(servers_entry.content)
    clock = SystemClock()
    arguments: dict[str, Any] = {}
    for item in arg or []:
        key, _, value = item.partition("=")
        arguments[key] = _value(value)
    if files is not None:
        arguments["files"] = {p.name: p.read_text() for p in sorted(files.iterdir()) if p.is_file()}
    scope = scope_for(spec_tool, spec) or spec_tool.scope

    class SpecPolicy:
        def authorize_decision(
            self, actor: str, action: str, resource: str, context: EvalContext
        ) -> tuple[bool, str]:
            return authorization.decide(actor, action, resource, context.run_id, spec)

        def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool:
            return self.authorize_decision(actor, action, resource, context)[0]

    host = str(servers.host_of(spec_tool.server))
    mcp = McpTool(
        spec_tool,
        host,
        McpClient(
            {"tools": settings.tools_url, "bridge": settings.pilot_bridge_url},
            settings.tools_timeout_s,
        ),
        settings.tools_token_key.get_secret_value(),
        BoundValues(SqlEvidenceProvider(engine, registry, clock), servers.bound_values),
        SqlToolRecords(engine, clock),
    )
    agent = AgentDefinition(
        "probe",
        "1.0.0",
        "model",
        "standard",
        None,
        (ToolBinding(tool, f"mcp:{spec_tool.server}:{scope}"),),
    )
    gate = ToolGate(SpecPolicy(), {tool: mcp})  # type: ignore[arg-type]
    reply = gate.call(
        run_id=run or f"{usecase}/{terminal}/probe",
        usecase_id=usecase,
        terminal_id=terminal,
        agent=agent,
        name=tool,
        arguments=arguments,
        spec=spec,
    )
    if isinstance(reply, ToolOutput):
        print(reply.text)
        return
    print(f"refused: {reply.reason}")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
