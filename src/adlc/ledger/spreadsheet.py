"""Spreadsheet uploads become artifact rows (contracts/artifacts.md; FR-011).

The sheet named after the artifact is used, else the only sheet. Row 1 holds the column names.
Cell values only: a formula reads as its saved value, or as an empty cell without one.
"""

import io
from datetime import date, datetime, time
from typing import Any

from openpyxl import load_workbook


class InvalidUpload(Exception):
    """The workbook cannot be read, or has no sheet that fits the artifact."""


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, bool | int | float | str):
        return value
    return str(value)


def read_rows(data: bytes, artifact_id: str) -> list[dict[str, Any]]:
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # any parse failure is an invalid upload
        raise InvalidUpload(f"the workbook cannot be read ({type(exc).__name__})") from exc
    try:
        names = book.sheetnames
        if artifact_id in names:
            sheet = book[artifact_id]
        elif len(names) == 1:
            sheet = book[names[0]]
        else:
            raise InvalidUpload(f"no sheet named {artifact_id} among {', '.join(names)}")
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        book.close()
    if not rows or all(cell is None for cell in rows[0]):
        raise InvalidUpload("no header row")
    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    out = []
    for row in rows[1:]:
        if all(cell is None or cell == "" for cell in row):
            continue
        out.append({name: _cell(value) for name, value in zip(header, row, strict=False) if name})
    return out
