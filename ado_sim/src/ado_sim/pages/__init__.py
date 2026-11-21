"""The simulator's pages (feature 017): sign-in, the board and the item page.

Server-rendered Jinja2 templates (autoescape on for every template, FR-012), HTMX for the board's
refresh, a hand-written stylesheet; every asset is served by the simulator itself (FR-014).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
TEMPLATES = Environment(
    loader=FileSystemLoader(HERE / "templates"),
    autoescape=select_autoescape(default=True, default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


def page(name: str, *, status: int = 200, **context: Any) -> HTMLResponse:
    return HTMLResponse(TEMPLATES.get_template(name).render(**context), status_code=status)
