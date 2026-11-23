"""Answer of ``/inbox`` (``adlc.inbox.service``): what waits for the signed-in person."""

from adlc.api.schemas.base import ApiModel, Timestamp


class InboxItem(ApiModel):
    kind: str
    id: str
    usecase_id: str | None
    terminal_id: str | None
    run_id: str | None
    role: str | None
    title: str
    arrived_at: Timestamp | None
    due_at: Timestamp | None
    controls_pending: bool
