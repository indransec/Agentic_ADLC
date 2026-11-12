"""T007: servers and scopes by host from the registry; the catalogue matches it."""

from pathlib import Path

import pytest

from adlc.tools.catalogue import CATALOGUE, ToolSpec
from adlc.tools.registry import Registry, RegistryError, scope_of

SPEC_DIR = Path(__file__).resolve().parents[3] / "adlc-specs"


def test_hosts_and_catalogue_agree() -> None:
    registry = Registry.load(SPEC_DIR)
    registry.check()
    bridge = {s.id for s in registry.on_host("bridge")}
    tools = {s.id for s in registry.on_host("tools")}
    assert {"pilot_env", "git", "ci", "harness", "cd", "kill_switch", "observability"} <= bridge
    assert {"servicenow", "cmdb", "agent_registry", "iam", "grc", "eval_store"} <= tools
    assert not bridge & tools
    assert all(registry.host_of(t.server) in ("tools", "bridge") for t in CATALOGUE.tools.values())


def test_unknown_server_or_scope_is_a_configuration_error() -> None:
    registry = Registry.load(SPEC_DIR)
    extra = ToolSpec("nowhere", "x", "read", "d")
    bad_scope = ToolSpec("git", "y", "admin", "d")
    from adlc.tools.catalogue import Catalogue

    for tool in (extra, bad_scope):
        with pytest.raises(RegistryError):
            registry.check(Catalogue({**CATALOGUE.tools, tool.full_name: tool}))


def test_environment_scope_comes_from_the_bound_environment() -> None:
    create = CATALOGUE.tools["pilot_env_create"]
    assert scope_of(create, "dev") == "mcp:pilot_env:dev"
    assert scope_of(create, "test") == "mcp:pilot_env:test"
    for bad in (None, "prod-sim"):
        with pytest.raises(RegistryError):
            scope_of(create, bad)
    assert scope_of(CATALOGUE.tools["cd_deploy"], None) == "mcp:cd:deploy"
