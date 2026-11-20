"""Work item comments (US5): add and list, api-version 7.1-preview.4.

Adding a comment records a new revision of the work item whose update carries
``System.CommentCount`` and ``System.History`` (T001: the reference's ``commentVersionRef``).
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from ado_sim.errors import invalid
from ado_sim.patch import MAX_VALUE_BYTES
from ado_sim.process import Identity
from ado_sim.workitems import WorkItemStore

MAX_TOP = 200
_LIST = (
    "SELECT c.*, i.display_name, i.unique_name FROM comment c"
    " JOIN identity i ON i.id = c.created_by WHERE c.work_item_id = ?"
)
_LIST_ASC = _LIST + " ORDER BY c.id ASC LIMIT ? OFFSET ?"
_LIST_DESC = _LIST + " ORDER BY c.id DESC LIMIT ? OFFSET ?"


@dataclass(frozen=True)
class CommentView:
    id: int
    work_item_id: int
    version: int
    text: str
    created_by: dict[str, Any]
    created_date: str
    modified_date: str


@dataclass(frozen=True)
class CommentPage:
    comments: list[CommentView]
    total: int
    continuation: str | None


def add_comment(store: WorkItemStore, item_id: int, text: Any, by: Identity) -> CommentView:
    if not isinstance(text, str) or not text.strip():
        raise invalid("A comment needs non-empty text.")
    if len(text.encode("utf-8")) > MAX_VALUE_BYTES:
        raise invalid("A comment may hold at most 1 MB of text.")
    with store.db.write() as conn:
        row = store._row(conn, item_id)
        fields = json.loads(row["fields"])
        fields["System.CommentCount"] = int(fields.get("System.CommentCount", 0)) + 1
        when = store.commit_change(conn, row, fields, by, transient={"System.History": text})
        cursor = conn.execute(
            "INSERT INTO comment (work_item_id, text, created_by, created_date, modified_date)"
            " VALUES (?, ?, ?, ?, ?)",
            (item_id, text, by.id, when, when),
        )
        return CommentView(int(cursor.lastrowid or 0), item_id, 1, text, by.reference(), when, when)


def _encode(order: str, offset: int) -> str:
    return base64.urlsafe_b64encode(f"{order}:{offset}".encode()).decode().rstrip("=")


def _decode(token: str, order: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        token_order, offset = raw.split(":")
        if token_order != order or int(offset) < 0:
            raise ValueError(token)
        return int(offset)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise invalid("The continuation token is not valid for this request.") from error


def list_comments(
    store: WorkItemStore,
    item_id: int,
    *,
    top: int | None = None,
    continuation: str | None = None,
    order: str = "desc",
) -> CommentPage:
    order = order.lower()
    if order not in ("asc", "desc"):
        raise invalid("order must be asc or desc.")
    limit = MAX_TOP if top is None else top
    if not 1 <= limit <= MAX_TOP:
        raise invalid(f"$top must be between 1 and {MAX_TOP}.")
    offset = _decode(continuation, order) if continuation else 0
    with store.db.read() as conn:
        store._row(conn, item_id)
        total = conn.execute(
            "SELECT COUNT(*) FROM comment WHERE work_item_id = ?", (item_id,)
        ).fetchone()[0]
        rows = conn.execute(
            _LIST_ASC if order == "asc" else _LIST_DESC, (item_id, limit, offset)
        ).fetchall()
    comments = [
        CommentView(
            int(r["id"]),
            item_id,
            int(r["version"]),
            r["text"],
            {
                "displayName": r["display_name"],
                "id": r["created_by"],
                "uniqueName": r["unique_name"],
            },
            r["created_date"],
            r["modified_date"],
        )
        for r in rows
    ]
    following = offset + len(comments)
    return CommentPage(
        comments, int(total), _encode(order, following) if following < total else None
    )
