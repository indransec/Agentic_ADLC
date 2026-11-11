"""T038: person-supplied file names are reduced to a safe last segment (spec edge case)."""

import pytest

from adlc.api.errors import Invalid
from adlc.api.routes.artifacts import MAX_NAME, safe_name


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("notes.md", "notes.md"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\notes.md", "notes.md"),
        ("bell\x07name\n.md", "bellname.md"),
        (None, "attachment"),
        ("x" * 300 + ".md", "x" * MAX_NAME),
    ],
)
def test_safe_names(raw: str | None, kept: str) -> None:
    assert safe_name(raw, "attachment") == kept


@pytest.mark.parametrize("raw", ["/", "../..", "dir/", "\x00\x01"])
def test_empty_names_are_refused(raw: str) -> None:
    with pytest.raises(Invalid):
        safe_name(raw, "attachment")
