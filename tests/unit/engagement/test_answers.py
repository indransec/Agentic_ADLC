"""Splitting a clarification answer into one answer per question (T036; inbound-rules §5)."""

import pytest

from adlc.engagement.inputs import Refusal, split_answers


def test_one_question_takes_the_whole_text() -> None:
    assert split_answers("  Yes, both regions.\nSee the KPI doc.  ", 1) == [
        "Yes, both regions.\nSee the KPI doc."
    ]


@pytest.mark.parametrize(
    "text",
    [
        "1. North\n2. Monthly",
        "1) North\n\n2) Monthly",
        "  1.  North\n  2.Monthly",
    ],
)
def test_numbered_answers(text: str) -> None:
    assert split_answers(text, 2) == ["North", "Monthly"]


def test_continuation_lines_join_their_answer() -> None:
    assert split_answers("1. North\nand South\n2. Monthly", 2) == ["North\nand South", "Monthly"]


@pytest.mark.parametrize(
    "text", ["1. North", "1. North\n2. Monthly\n3. Extra", "North\nMonthly", "2. a\n1. b"]
)
def test_a_count_mismatch_is_refused(text: str) -> None:
    result = split_answers(text, 2)
    assert isinstance(result, Refusal) and result.code == "invalid_input"
    assert "2" in result.message


def test_an_empty_answer_is_refused() -> None:
    assert isinstance(split_answers("   ", 1), Refusal)
