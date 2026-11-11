"""A built default package and variant package in a temporary registry, and host factories."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pilot_tools.build import build
from pilot_tools.host import create_host
from tests.conftest import DEFAULT_FILL, TEMPLATE, VARIANT_FILL


@dataclass
class Packages:
    registry: Path
    default: str
    variant: str


@pytest.fixture(scope="session")
def packages(tmp_path_factory: pytest.TempPathFactory) -> Packages:
    registry = tmp_path_factory.mktemp("registry")
    return Packages(
        registry,
        build(TEMPLATE, DEFAULT_FILL, registry).package_hash,
        build(TEMPLATE, VARIANT_FILL, registry).package_hash,
    )


@dataclass
class Host:
    client: TestClient
    records: Path

    def record(self, name: str) -> list[dict[str, Any]]:
        path = self.records / f"{name}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def host(packages: Packages, tmp_path: Path) -> Iterator[Callable[[str], Host]]:
    opened: list[TestClient] = []

    def make(environment: str) -> Host:
        records = tmp_path / f"records-{environment}"
        app = create_host(
            environment, TEMPLATE, packages.registry, tmp_path / f"work-{environment}", records
        )
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return Host(client, records)

    yield make
    for client in opened:
        client.__exit__(None, None, None)
