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
PILOT_CODE = sorted((ROOT / "pilot").rglob("*.py"))
PILOT_MODULES = ("pilot_tools", "triage_agent")
SHARED = {"jaeger"}  # the shared trace collector joins both networks (research R-09)


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
        if name.startswith("pilot-"):
            assert not service.get("ports"), name
        for volume in service.get("volumes") or []:
            assert "docker.sock" not in str(volume), name
