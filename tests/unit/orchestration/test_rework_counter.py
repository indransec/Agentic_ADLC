"""T035: the rework rule (research R-05; FR-019, FR-020)."""

from hypothesis import given
from hypothesis import strategies as st

from adlc.orchestration import routing

events = st.sampled_from(
    [
        "T0.pass",
        "T1.rework.requirement",
        "T4.rework.requirement",
        "T9.reentry.T1",
        "T2.rework.requirement",
    ]
)


@given(st.lists(events, max_size=20), events)
def test_count_is_reworks_so_far_plus_this_one(history: list[str], event: str) -> None:
    expected = sum(".rework." in e for e in history) + (".rework." in event)
    assert routing.rework_count(history, event) == expected


def test_limit_is_exclusive() -> None:
    assert [routing.over_rework_limit(n, 3) for n in range(6)] == [
        False,
        False,
        False,
        False,
        True,
        True,
    ]
