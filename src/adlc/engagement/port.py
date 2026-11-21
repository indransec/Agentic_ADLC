"""The ``BoardAdapter`` port (contracts/board-port.md, constitution VII).

The engagement layer reaches a tracker only through this protocol. ``AdoBoard`` (``ado.py``) and
``FakeBoard`` (``fake.py``) implement it and pass the same contract suite
(``tests/contract/board/``). Error messages never carry field values or tokens.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from adlc.engagement.model import BoardInfo, BoardItem, BoardUpdate, ChangePage, Identity, ItemWrite


class BoardError(Exception):
    """Base of every board failure the engagement layer handles."""


class BoardUnreachable(BoardError):
    """The board did not answer (timeout, connection refused, 5xx); retry later."""


class BoardAuthFailed(BoardError):
    """The service account's token was refused (401)."""


class ItemNotFound(BoardError):
    """No such work item (404)."""


class RevisionConflict(BoardError):
    """The item is no longer at the expected revision (412); nothing was changed."""


class BoardRefused(BoardError):
    """The board refused the request as invalid (400): an unknown field, value or state."""


class BoardAdapter(Protocol):
    def check(self) -> BoardInfo:
        """Authenticate as the service account and describe the board's process and areas."""
        ...

    def create(
        self, item_type: str, fields: Mapping[str, Any], parent_id: int | None = None
    ) -> BoardItem:
        """Create an item (and its link to ``parent_id``) as the service account."""
        ...

    def get(self, item_id: int) -> BoardItem: ...

    def get_at(self, item_id: int, rev: int) -> BoardItem:
        """The item exactly as of revision ``rev``."""
        ...

    def update(self, item_id: int, write: ItemWrite) -> BoardItem:
        """Set and clear fields, all or nothing; ``RevisionConflict`` if not at ``expected_rev``."""
        ...

    def comment(self, item_id: int, text: str) -> None:
        """Add a comment as the service account."""
        ...

    def changed_since(self, watermark: str | None) -> ChangePage:
        """Items changed at or after ``watermark`` (all items when None), and the next ``as_of``."""
        ...

    def updates(self, item_id: int, after_update_id: int = 0) -> list[BoardUpdate]:
        """The item's updates after ``after_update_id``, in order."""
        ...

    def find_identity(self, unique_name: str) -> Identity | None: ...
