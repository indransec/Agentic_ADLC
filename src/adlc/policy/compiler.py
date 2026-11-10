"""Compile spec expressions once and list what they read (research R-01, R-02).

Programs are cached by expression text. References come from the 002 parser, so evaluation and
validation agree on what an expression reads. A parse error is returned, never raised.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import celpy

from adlc.spec_toolkit.expressions import ExpressionError, parse_expression

_ENV = celpy.Environment()


@dataclass(frozen=True)
class Compiled:
    text: str
    ast: Any | None
    error: str | None
    refs: tuple[tuple[str, ...], ...]
    calls: tuple[str, ...]

    @property
    def roots(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r[0] for r in self.refs))


@lru_cache(maxsize=4096)
def compile_rule(text: str) -> Compiled:
    try:
        parsed = parse_expression(text)
        ast = _ENV.compile(text)
    except ExpressionError as exc:
        return Compiled(text, None, str(exc), (), ())
    except Exception as exc:  # celpy parse errors: fail closed, never raise
        return Compiled(
            text, None, str(exc).splitlines()[0] if str(exc) else "cannot parse", (), ()
        )
    refs = tuple(dict.fromkeys(r.path for r in parsed.refs))
    calls = tuple(dict.fromkeys(c.name for c in parsed.calls))
    return Compiled(text, ast, None, refs, calls)


@lru_cache(maxsize=4096)
def program(text: str, functions_key: int) -> Any:
    """A runnable program for ``text`` (``functions_key`` ties the cache to one library)."""
    compiled = compile_rule(text)
    if compiled.ast is None:
        raise ValueError(compiled.error or "cannot compile")
    return _ENV.program(compiled.ast, functions=_FUNCTIONS[functions_key])


_FUNCTIONS: dict[int, dict[str, Any]] = {}


def register_functions(functions: dict[str, Any]) -> int:
    key = id(functions)
    _FUNCTIONS[key] = functions
    return key
