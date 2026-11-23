"""Answer of ``/inbox`` (``adlc.inbox.service``): what waits for the signed-in person."""

from pydantic import Field

from adlc.api.schemas.base import ApiModel, Timestamp


class InboxItem(ApiModel):
    kind: str = Field(
        description="sign_off, clarification, escalation, waiver, blocked or dead_letter"
    )
    id: str = Field(description="The run, clarification, waiver or event it is about")
    usecase_id: str | None
    terminal_id: str | None
    run_id: str | None
    role: str | None = Field(description="The person's role it is addressed to")
    title: str = Field(description="Platform words for the item")
    arrived_at: Timestamp | None
    due_at: Timestamp | None
    controls_pending: bool
