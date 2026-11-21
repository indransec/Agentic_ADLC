"""019: the ADO adapter's address of an item for browsers (research R-03)."""

from __future__ import annotations

from adlc.engagement.ado import AdoBoard

TOKEN = "t" * 52


def test_ado_item_url_uses_the_public_address_and_quotes_the_names() -> None:
    board = AdoBoard(
        base_url="http://ado-sim:8600",
        public_url="http://localhost:8600/",
        organization="adlc-demo",
        project="Agentic ADLC",
        token=TOKEN,
    )
    assert board.item_url(42) == "http://localhost:8600/adlc-demo/Agentic%20ADLC/_workitems/edit/42"


def test_ado_item_url_defaults_to_the_base_url() -> None:
    board = AdoBoard(base_url="https://dev.azure.com", organization="org", project="P", token=TOKEN)
    assert board.item_url(7) == "https://dev.azure.com/org/P/_workitems/edit/7"
    assert TOKEN not in repr(board)
