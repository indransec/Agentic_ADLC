"""013 T002 (research R-04): a run's time split from its state transitions."""

from datetime import UTC, datetime, timedelta

from adlc.dashboard.timesplit import CATEGORIES, Transition, split

T0 = datetime(2026, 11, 13, 9, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_states_map_to_categories() -> None:
    transitions = [
        Transition("opened", at(0)),
        Transition("building", at(1)),
        Transition("awaiting_clarification", at(5)),
        Transition("building", at(25)),
        Transition("checking", at(30)),
        Transition("reviewing", at(31)),
        Transition("awaiting_sign_off", at(35)),
        Transition("closed", at(95)),
    ]
    assert split(transitions, now=at(200)) == {
        "agent": 9 * 60.0,
        "reviewer": 5 * 60.0,
        "clarification": 20 * 60.0,
        "people": 60 * 60.0,
        "blocked": 0.0,
        "other": 60.0,  # opened: the orchestrator checking prerequisites
    }


def test_an_open_run_counts_until_now() -> None:
    found = split([Transition("blocked", at(0)), Transition("escalated", at(10))], now=at(40))
    assert found["blocked"] == 600.0 and found["people"] == 1800.0


def test_categories_are_fixed() -> None:
    assert CATEGORIES == ("agent", "reviewer", "clarification", "people", "blocked", "other")
    assert split([], now=at(0)) == dict.fromkeys(CATEGORIES, 0.0)
