"""What a predicate can see while it runs, and how it explains a failure.

The engine binds a ``CallContext`` for the duration of one evaluation (a context variable), so
predicates stay plain functions of their catalogued arguments. A predicate that fails calls
``fail(reason)``; the first reason becomes the decision's reason (research R-02).
"""

import contextlib
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from celpy import celtypes

from adlc.orchestration.interfaces import EvalContext, EvalResult
from adlc.policy.evidence import Answer
from adlc.policy.values import to_py


class PredicateError(Exception):
    """An argument has the wrong shape; the evaluation fails closed with this message."""


class Table(celtypes.ListType):
    """A list of rows that remembers where it came from, for failure reasons."""

    ref: str = "table"

    @classmethod
    def named(cls, rows: list[Any], ref: str) -> "Table":
        table = cls(rows)
        table.ref = ref
        return table


class Record(celtypes.MapType):
    """A mapping that remembers where it came from, for failure reasons."""

    ref: str = "value"

    @classmethod
    def named(cls, items: Mapping[Any, Any], ref: str) -> "Record":
        record = cls(items)
        record.ref = ref
        return record


@dataclass
class CallContext:
    eval: EvalContext
    fetch: Callable[[str], Answer]
    catalogue: Callable[[str], Mapping[str, Any] | None]
    spec: Mapping[str, Any] | None
    nested: Callable[[str, str], EvalResult]
    now: datetime
    reasons: list[str] = field(default_factory=list)


_CURRENT: ContextVar[CallContext] = ContextVar("adlc_policy_call")


def bind(ctx: CallContext) -> Any:
    return _CURRENT.set(ctx)


def unbind(token: Any) -> None:
    _CURRENT.reset(token)


def current() -> CallContext:
    return _CURRENT.get()


def fail(reason: str) -> celtypes.BoolType:
    with contextlib.suppress(LookupError):
        current().reasons.append(reason)
    return celtypes.BoolType(False)


def ok() -> celtypes.BoolType:
    return celtypes.BoolType(True)


def verdict(passed: bool, reason: str) -> celtypes.BoolType:
    return ok() if passed else fail(reason)


def name_of(value: Any) -> str:
    return getattr(value, "ref", "table")


def rows(value: Any) -> list[dict[str, Any]]:
    """The rows of a table argument; anything else is an error (fails closed)."""
    plain = to_py(value)
    if not isinstance(plain, list) or not all(isinstance(r, dict) for r in plain):
        raise PredicateError(f"{name_of(value)} is not a table")
    return plain


def strings(value: Any) -> list[str]:
    plain = to_py(value)
    if not isinstance(plain, list):
        raise PredicateError("expected a list")
    return [str(v) for v in plain]


def catalogue_items(name: str, key: str) -> list[dict[str, Any]]:
    content = current().catalogue(name) or {}
    items = content.get(key, [])
    return [dict(i) for i in items] if isinstance(items, list) else []
