"""Records, signatures, waivers and the directory (contracts/predicates.md)."""

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from adlc.orchestration import durations
from adlc.policy.evidence import Evidence
from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import (
    PredicateError,
    current,
    fail,
    name_of,
    ok,
    strings,
    verdict,
)
from adlc.policy.values import is_empty, is_truthy, text, to_py

SIGNED = ("pass", "exception")
_TERMINAL = re.compile(r"^([A-Z][0-9]+)\.")


def _terminal_record(ref: Any) -> tuple[str, Mapping[str, Any]]:
    match = _TERMINAL.match(name_of(ref))
    if match is None:
        raise PredicateError(f"{name_of(ref)} is not terminal evidence")
    terminal = match.group(1)
    answer = current().fetch(terminal)
    if not isinstance(answer, Evidence) or not isinstance(answer.value, Mapping):
        raise PredicateError(f"evidence not available: {terminal}")
    return terminal, answer.value


def _source(name: str) -> Any:
    answer = current().fetch(name)
    if not isinstance(answer, Evidence):
        raise PredicateError(f"evidence not available: {name}")
    return answer.value


def _date(value: Any) -> date:
    plain = to_py(value)
    if isinstance(plain, datetime):
        return plain.date()
    if isinstance(plain, date):
        return plain
    try:
        return date.fromisoformat(text(plain)[:10])
    except ValueError as exc:
        raise PredicateError(f"not a date: {plain!r}") from exc


@predicate("evidence_exists", 1)
def evidence_exists(ref: Any) -> Any:
    return verdict(not is_empty(ref), f"{name_of(ref)} is empty")


@predicate("is_signed", 1)
def is_signed(ref: Any) -> Any:
    terminal, record = _terminal_record(ref)
    status = text(record.get("status"))
    return verdict(status in SIGNED, f"{terminal} is not signed (status {status})")


@predicate("is_frozen", 1)
def is_frozen(ref: Any) -> Any:
    terminal, record = _terminal_record(ref)
    return verdict(text(record.get("status")) != "open", f"{terminal} run is still open")


@predicate("is_live", 1)
def is_live(ref: Any) -> Any:
    terminal, record = _terminal_record(ref)
    status = text(record.get("status"))
    if status not in SIGNED:
        return fail(f"{terminal} is not live (status {status})")
    rows = to_py(ref)
    if isinstance(rows, list):
        for i, row in enumerate(rows, start=1):
            if isinstance(row, dict) and "status" in row and text(row["status"]).lower() != "live":
                return fail(f"{name_of(ref)} row {i}: status is {row['status']!r}, not live")
    return ok()


@predicate("is_provisioned", 1)
def is_provisioned(ref: Any) -> Any:
    value = to_py(ref)
    passed = isinstance(value, dict) and is_truthy(value.get("provisioned"))
    return verdict(passed, f"{name_of(ref)} is not provisioned")


@predicate("is_pinned", 1)
def is_pinned(ref: Any) -> Any:
    value = to_py(ref)
    if isinstance(value, dict):
        return verdict(is_truthy(value.get("pinned")), f"{name_of(ref)} is not pinned")
    version = text(value)
    pinned = bool(version) and version.lower() != "latest" and "*" not in version
    return verdict(pinned, f"version {version!r} is not pinned")


@predicate("in_directory", 1)
def in_directory(person: Any) -> Any:
    names = _source("directory")
    name = text(person)
    return verdict(name in {str(n) for n in names}, f"{name!r} is not in the directory")


@predicate("approved_by", 2)
def approved_by(ref: Any, role: Any) -> Any:
    wanted = text(role)
    value = to_py(ref)
    if isinstance(value, dict) and wanted in [str(r) for r in value.get("approved_by") or []]:
        return ok()
    if _TERMINAL.match(name_of(ref)):
        terminal, record = _terminal_record(ref)
        if wanted in [str(r) for r in record.get("signed_roles") or []]:
            return ok()
    return fail(f"{name_of(ref)} is not approved by {wanted}")


@predicate("all_statuses_in", 2)
def all_statuses_in(terminals: Any, statuses: Any) -> Any:
    allowed = set(strings(statuses))
    for terminal in strings(terminals):
        answer = current().fetch(terminal)
        if not isinstance(answer, Evidence):
            return fail(f"{terminal} has no closed run")
        status = text(answer.value.get("status"))
        if status not in allowed:
            return fail(f"{terminal} status is {status}, not one of {sorted(allowed)}")
    return ok()


def _waivers() -> list[dict[str, Any]]:
    value = _source("waivers")
    return [dict(w) for w in value] if isinstance(value, list) else []


@predicate("no_waiver_expiring_before", 1)
def no_waiver_expiring_before(when: Any) -> Any:
    limit = _date(when)
    for waiver in _waivers():
        if waiver.get("expiry") is not None and _date(waiver["expiry"]) < limit:
            return fail(f"waiver {waiver['waiver_id']} expires {waiver['expiry']} before {limit}")
    return ok()


@predicate("no_expired_waivers", 0)
def no_expired_waivers() -> Any:
    today = current().now.date()
    for waiver in _waivers():
        if waiver.get("expiry") is not None and _date(waiver["expiry"]) < today:
            return fail(f"waiver {waiver['waiver_id']} expired on {waiver['expiry']}")
    return ok()


@predicate("waiver_expiring_within", 1)
def waiver_expiring_within(period: Any) -> Any:
    plain = to_py(period)
    window = plain if isinstance(plain, timedelta) else durations.parse(text(plain))
    limit = (current().now + window).date()
    today = current().now.date()
    for waiver in _waivers():
        expiry = waiver.get("expiry")
        if expiry is not None and today <= _date(expiry) <= limit:
            return ok()
    return fail(f"no waiver expires within {plain}")
