"""Measured success criteria of the engagement layer print in the test summary (016 T059)."""

from typing import Any

MEASUREMENTS: dict[str, str] = {}


def pytest_terminal_summary(terminalreporter: Any) -> None:
    if MEASUREMENTS:
        terminalreporter.section("board engagement measurements")
        for name, value in MEASUREMENTS.items():
            terminalreporter.write_line(f"{name}: {value}")
