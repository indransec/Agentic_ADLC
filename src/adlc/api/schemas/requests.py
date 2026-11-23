"""Answers of the request routes: dead letters (clarification and waiver answers are runs)."""

from typing import Any
from uuid import UUID

from adlc.api.schemas.base import ApiModel, Record, Timestamp


class DeadLetter(ApiModel):
    event_id: UUID | str
    event_type: str
    usecase_id: str | None
    causation_run_id: str | None
    attempts: int
    last_error: str | None
    dead_lettered_at: Timestamp | None
    requeues: int


class DeadLetterDetail(ApiModel):
    event_id: UUID | str
    event_type: str
    usecase_id: str | None
    causation_run_id: str | None
    attempts: int
    last_error: str | None
    dead_lettered_at: Timestamp | None
    processed_at: Timestamp | None
    payload: Any
    history: list[Record]
