"""Answers of ``/changes`` (feature 012): change requests waiting for the ITSM approver."""

from pydantic import ConfigDict

from adlc.api.schemas.base import ApiModel


class ChangeRequest(ApiModel):
    """A change request: the record's own fields (summary, window, risk, plan, state, and the
    decision once made) are the ITSM body, open by nature; the fields below are the platform's."""

    model_config = ConfigDict(extra="allow")

    change_id: str
    record_version: int
    usecase_id: str | None
    run_id: str | None
    terminal_id: str | None
    at: str
