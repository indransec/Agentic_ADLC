"""Fail-fast reporting for settings (contracts/settings.md "Failure output", FR-014, FR-015).

Output names the variable and the expected form. Input values are never printed.
"""

import sys
from typing import NoReturn

from pydantic import ValidationError
from pydantic_settings import BaseSettings

from adlc.config.settings import env_name

HEADER = "adlc: configuration error"
EXIT_CODE = 2


def _describe(model: type[BaseSettings], field_name: str) -> tuple[str, bool]:
    field = model.model_fields.get(field_name)
    extra = field.json_schema_extra if field is not None else None
    if isinstance(extra, dict):
        return str(extra.get("form", "a valid value")), bool(extra.get("secret", False))
    return "a valid value", False


def format_settings_error(exc: ValidationError, model: type[BaseSettings]) -> str:
    lines = [HEADER]
    seen: set[str] = set()
    for error in exc.errors(include_input=False, include_url=False):
        field_name = str(error["loc"][0]) if error["loc"] else ""
        if field_name in seen:
            continue
        seen.add(field_name)
        problem = "missing" if error["type"] == "missing" else "invalid"
        form, secret = _describe(model, field_name)
        suffix = " (secret)" if secret else ""
        lines.append(f"  {env_name(field_name)}: {problem}; expected {form}{suffix}")
    return "\n".join(lines) + "\n"


def load_settings_or_exit[S: BaseSettings](model: type[S]) -> S:
    """Build settings from the environment, or print the problems and exit with code 2."""
    try:
        return model()
    except ValidationError as exc:
        _exit(format_settings_error(exc, model))


def _exit(message: str) -> NoReturn:
    sys.stderr.write(message)
    sys.exit(EXIT_CODE)
