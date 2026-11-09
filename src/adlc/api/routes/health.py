"""``GET /health``: service health without authentication (FR-003, contracts/platform-api)."""

import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)
router = APIRouter()

CheckState = Literal["ok", "unavailable"]


class Health(BaseModel):
    status: CheckState
    checks: dict[str, CheckState]


def _database(engine: Engine) -> CheckState:
    try:
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = 2000"))
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.warning("health: database check failed")
        return "unavailable"
    return "ok"


@router.get("/health", response_model=Health)
def health(request: Request, response: Response) -> Health:
    checks: dict[str, CheckState] = {"database": _database(request.app.state.engine)}
    healthy = all(state == "ok" for state in checks.values())
    if not healthy:
        response.status_code = 503
    return Health(status="ok" if healthy else "unavailable", checks=checks)
