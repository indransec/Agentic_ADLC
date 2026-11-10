"""T014: spreadsheet uploads become rows (contracts/artifacts.md)."""

import io
from datetime import date

import pytest
from openpyxl import Workbook

from adlc.ledger.spreadsheet import InvalidUpload, read_rows


def _workbook(sheets: dict[str, list[list[object]]]) -> bytes:
    book = Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = book.active if first else book.create_sheet()
        assert sheet is not None
        sheet.title = name
        first = False
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_named_sheet_and_kinds() -> None:
    data = _workbook(
        {
            "notes": [["x"], [1]],
            "kpis": [
                [" kpi ", "baseline", "live", "since"],
                ["handle time", 12, True, date(2026, 1, 2)],
                [None, None, None, None],
                ["csat", 3.9, False, None],
            ],
        }
    )
    assert read_rows(data, "kpis") == [
        {"kpi": "handle time", "baseline": 12, "live": True, "since": "2026-01-02T00:00:00"},
        {"kpi": "csat", "baseline": 3.9, "live": False, "since": ""},
    ]


def test_only_sheet_is_used() -> None:
    assert read_rows(_workbook({"Sheet1": [["a"], ["1"]]}), "kpis") == [{"a": "1"}]


def test_formula_without_saved_value_is_empty() -> None:
    assert read_rows(_workbook({"kpis": [["a", "b"], [1, "=A2*2"]]}), "kpis") == [{"a": 1, "b": ""}]


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"not a workbook", "cannot be read"),
        (_workbook({"a": [["x"]], "b": [["y"]]}), "no sheet named kpis"),
        (_workbook({"kpis": []}), "no header row"),
    ],
)
def test_refusals(data: bytes, reason: str) -> None:
    with pytest.raises(InvalidUpload, match=reason):
        read_rows(data, "kpis")
