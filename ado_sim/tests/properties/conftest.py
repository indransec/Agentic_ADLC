"""Shared helpers for the success-criteria properties; measured timings print in the summary."""

from __future__ import annotations

from typing import Any

import pytest

from ado_sim.db import Database
from ado_sim.process import Identity, identity_by_name
from tests.pages.conftest import client  # noqa: F401 - the page client fixture for 017's properties

MEASUREMENTS: dict[str, str] = {}

WRITERS = (
    "adlc-platform@adlc.demo",
    "product.owner@adlc.demo",
    "solution.architect@adlc.demo",
    "engineering.lead@adlc.demo",
)


def identities(db: Database, names: tuple[str, ...] = WRITERS) -> list[Identity]:
    with db.read() as conn:
        found = [identity_by_name(conn, name) for name in names]
    assert all(found)
    return [identity for identity in found if identity is not None]


def percentile(samples: list[float], share: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def pytest_terminal_summary(terminalreporter: Any) -> None:
    if MEASUREMENTS:
        terminalreporter.section("ADO simulator measurements")
        for name, value in MEASUREMENTS.items():
            terminalreporter.write_line(f"{name}: {value}")


@pytest.fixture
def measurements() -> dict[str, str]:
    return MEASUREMENTS
