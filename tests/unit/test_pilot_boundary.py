"""009 T004: the pilot is any team's agent. Neither side imports the other, and Compose keeps the
pilot on its own network (FR-013, FR-017; SC-007)."""

import ast
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose.yaml"
PLATFORM_CODE = sorted((ROOT / "src" / "adlc").rglob("*.py"))
PILOT_CODE = sorted(
    p for folder in ("src", "template", "tests") for p in (ROOT / "pilot" / folder).rglob("*.py")
)
PILOT_MODULES = ("pilot_tools", "triage_agent")
SHARED = {"jaeger", "pilot-bridge"}  # trace collector (009 R-09) and the MCP bridge (010 R-01)
BRIDGE = "pilot-bridge"
BRIDGE_MUST_NOT_HAVE = ("ADLC_DB_", "_API_KEY", "ADLC_KNOWLEDGE_TOKEN", "ADLC_SESSION_SECRET")


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", PLATFORM_CODE, ids=lambda p: str(p.relative_to(ROOT)))
def test_platform_never_imports_the_pilot(path: Path) -> None:
    assert sorted(n for n in imported(path) if n.split(".")[0] in PILOT_MODULES) == []


@pytest.mark.parametrize("path", PILOT_CODE, ids=lambda p: str(p.relative_to(ROOT)))
def test_pilot_never_imports_the_platform(path: Path) -> None:
    assert sorted(n for n in imported(path) if n.split(".")[0] == "adlc") == []


def services() -> dict[str, Any]:
    return dict(YAML(typ="safe").load(COMPOSE.read_text())["services"])


def networks(service: dict[str, Any]) -> set[str]:
    value = service.get("networks") or ["default"]
    return set(value) if isinstance(value, list) else set(dict(value))


def test_pilot_services_exist() -> None:
    pilots = {name for name in services() if name.startswith("pilot-")}
    assert {"pilot-dev", "pilot-test", "pilot-prodsim", "pilot-traffic", "pilot-tools"} <= pilots


@pytest.mark.xfail(strict=True, reason="010: Compose services arrive with US1, US2 and US6")
def test_tool_services_exist() -> None:
    assert {"tools", "pilot-bridge", "pilot-lab"} <= set(services())


def test_the_bridge_holds_no_database_model_or_session_settings() -> None:
    """010 R-01: the only service on both networks gets the least."""
    bridge = services().get(BRIDGE)
    if bridge is None:
        pytest.skip("pilot-bridge not in Compose yet")
    environment = bridge.get("environment") or {}
    names = (
        set(environment)
        if isinstance(environment, dict)
        else {str(e).split("=")[0] for e in environment}
    )
    assert not any(part in n for n in names for part in BRIDGE_MUST_NOT_HAVE), sorted(names)
    assert not bridge.get("ports")


def test_networks_keep_pilot_and_platform_apart() -> None:
    for name, service in services().items():
        joined = networks(service)
        if name in SHARED:
            assert joined == {"platform", "pilot"}, name
        elif name.startswith("pilot-"):
            assert joined == {"pilot"}, name
        else:
            assert joined == {"platform"}, name


def test_pilot_publishes_no_ports_and_nothing_mounts_the_docker_socket() -> None:
    for name, service in services().items():
        if name.startswith("pilot-") or name == "tools":
            assert not service.get("ports"), name
        for volume in service.get("volumes") or []:
            assert "docker.sock" not in str(volume), name


def test_pilot_reads_only_its_own_settings() -> None:
    """009 A3: the pilot reads only PILOT_* variables (and process basics), never ADLC_* ones."""
    import re

    pattern = re.compile(r"environ(?:\.get)?\(\s*[\"']([A-Z_]+)[\"']|environ\[\s*[\"']([A-Z_]+)")
    read: set[str] = set()
    for path in PILOT_CODE:
        for found in pattern.findall(path.read_text()):
            read |= {name for name in found if name}
    assert read and all(name.startswith("PILOT_") for name in read), sorted(read)
