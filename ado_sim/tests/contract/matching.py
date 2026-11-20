"""Match a response body against a fixture's body pattern (contract/fixtures/README.md)."""

from __future__ import annotations

import re
from typing import Any

_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_URL = re.compile(r"^https?://\S+$")
MORE = "<more>"


def _scalar(pattern: str, value: Any) -> bool:
    if pattern == "<any>":
        return True
    if pattern == "<int>":
        return isinstance(value, int) and not isinstance(value, bool)
    if pattern == "<string>":
        return isinstance(value, str)
    checks = {"<datetime>": _DATETIME, "<uuid>": _UUID, "<url>": _URL}
    return isinstance(value, str) and bool(checks[pattern].match(value))


def mismatches(pattern: Any, value: Any, where: str = "$") -> list[str]:
    """Every place where ``value`` does not match ``pattern``; empty when it matches."""
    if isinstance(pattern, str) and pattern in (
        "<any>",
        "<int>",
        "<string>",
        "<datetime>",
        "<uuid>",
        "<url>",
    ):
        return [] if _scalar(pattern, value) else [f"{where}: {value!r} is not {pattern}"]
    if isinstance(pattern, dict):
        if not isinstance(value, dict):
            return [f"{where}: expected an object, got {value!r}"]
        problems = [f"{where}: missing key {k!r}" for k in pattern if k not in value]
        problems += [f"{where}: unexpected key {k!r}" for k in value if k not in pattern]
        for key in pattern.keys() & value.keys():
            problems += mismatches(pattern[key], value[key], f"{where}.{key}")
        return problems
    if isinstance(pattern, list):
        if not isinstance(value, list):
            return [f"{where}: expected a list, got {value!r}"]
        open_ended = bool(pattern) and pattern[-1] == MORE
        items = pattern[:-1] if open_ended else pattern
        if len(value) < len(items) or (not open_ended and len(value) != len(items)):
            return [f"{where}: expected {len(items)} items, got {len(value)}"]
        problems = []
        for index, item in enumerate(items):
            problems += mismatches(item, value[index], f"{where}[{index}]")
        return problems
    if pattern != value or type(pattern) is not type(value):
        return [f"{where}: expected {pattern!r}, got {value!r}"]
    return []
