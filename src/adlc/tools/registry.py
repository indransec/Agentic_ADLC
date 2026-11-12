"""Servers, scopes and hosts from the MCP registry (feature 010, research R-01, R-13).

``adlc-specs/shared/mcp_servers.yaml`` says which process serves each server (``host``); the tool
catalogue says what each server offers. A tool whose server or scope is not in the registry is a
configuration error, found at start-up.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from adlc.tools.catalogue import CATALOGUE, ENVIRONMENT_SCOPE, Catalogue, ToolSpec

REGISTRY_FILE = Path("shared") / "mcp_servers.yaml"
TOOL_HOSTS = ("tools", "bridge")
ENVIRONMENT_SCOPES = ("dev", "test")


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class Server:
    id: str
    host: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class Registry:
    servers: Mapping[str, Server]
    bound_values: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, spec_dir: Path) -> "Registry":
        return cls.from_content(YAML(typ="safe").load((spec_dir / REGISTRY_FILE).read_text()))

    @classmethod
    def from_content(cls, data: Mapping[str, Any]) -> "Registry":
        servers = {
            str(s["id"]): Server(str(s["id"]), str(s["host"]), tuple(str(x) for x in s["scopes"]))
            for s in data.get("mcp_servers") or []
        }
        bound = {str(k): str(v) for k, v in dict(data.get("bound_values") or {}).items()}
        return cls(servers, bound)

    def on_host(self, host: str) -> list[Server]:
        return sorted((s for s in self.servers.values() if s.host == host), key=lambda s: s.id)

    def host_of(self, server: str) -> str | None:
        found = self.servers.get(server)
        return None if found is None else found.host

    def check(self, catalogue: Catalogue = CATALOGUE) -> None:
        """Every catalogued tool's server and scope exist, and every tool server has tools."""
        problems: list[str] = []
        for tool in catalogue.tools.values():
            server = self.servers.get(tool.server)
            if server is None:
                problems.append(f"{tool.full_name}: server {tool.server} is not in the registry")
                continue
            scopes = ENVIRONMENT_SCOPES if tool.scope == ENVIRONMENT_SCOPE else (tool.scope,)
            missing = [s for s in scopes if s not in server.scopes]
            if missing:
                problems.append(f"{tool.full_name}: scope {', '.join(missing)} not registered")
        for server in self.servers.values():
            if server.host in TOOL_HOSTS and not catalogue.for_server(server.id):
                problems.append(f"server {server.id} on {server.host} has no tools")
        if problems:
            raise RegistryError("; ".join(problems))

    def tools_on(self, host: str, catalogue: Catalogue = CATALOGUE) -> dict[str, list[ToolSpec]]:
        return {s.id: catalogue.for_server(s.id) for s in self.on_host(host)}


def scope_of(tool: ToolSpec, environment: str | None) -> str:
    """The ``mcp:<server>:<scope>`` a call needs; environment-scoped tools use the bound one."""
    scope = environment if tool.scope == ENVIRONMENT_SCOPE else tool.scope
    if scope is None or (tool.scope == ENVIRONMENT_SCOPE and scope not in ENVIRONMENT_SCOPES):
        raise RegistryError(f"{tool.full_name} needs a bound environment (dev or test)")
    return f"mcp:{tool.server}:{scope}"
