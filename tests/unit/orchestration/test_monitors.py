"""012 T015 (FR-007, research R-02): declared monitors are evaluated through the policy engine;
one event per breach episode; an unevaluable or synthetic threshold never fires."""

from adlc.orchestration.interfaces import EvalContext, EvalResult
from adlc.orchestration.monitors import Monitor, declared_monitors, step

SPEC = {
    "terminal": {
        "metadata": {"id": "T8"},
        "monitors": [
            {
                "id": "MON-04",
                "signal": "eval.online_score",
                "threshold": "below(x)",
                "raises": "T8.event.drift",
            },
            {"id": "MON-09", "signal": "s", "threshold": "t", "raises": "T8.escalate"},
        ],
    }
}


def test_declared_monitors_come_from_the_spec() -> None:
    assert declared_monitors(SPEC) == (
        Monitor("MON-04", "eval.online_score", "below(x)", "drift"),
    )  # only operational events (<terminal>.event.<name>) are raised by monitors
    assert declared_monitors({"terminal": {"metadata": {"id": "T1"}}}) == ()


class Policy:
    def __init__(self, result: EvalResult) -> None:
        self.result = result
        self.calls: list[tuple[str, EvalContext]] = []

    def evaluate(self, expression: str, context: EvalContext) -> EvalResult:
        self.calls.append((expression, context))
        return self.result

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool:
        return False


BREACH = EvalResult(True, True, "passed")
CLEAR = EvalResult(False, False, "rule is false")
UNDECIDED = EvalResult(False, None, "evidence not available: telemetry")
MONITOR = Monitor("MON-04", "eval.online_score", "below(x)", "drift")


def _step(result: EvalResult, previous: str | None) -> tuple[bool, Policy]:
    policy = Policy(result)
    fires = step(policy, MONITOR, EvalContext("T8", "MON-04", "UC-1/T8/run-1", "UC-1"), previous)
    return fires, policy


def test_a_new_breach_fires_once() -> None:
    assert _step(BREACH, None)[0]
    assert _step(BREACH, "clear")[0]
    assert _step(BREACH, "undecided")[0]
    assert not _step(BREACH, "breach")[0]  # the same episode


def test_clear_and_undecided_never_fire() -> None:
    for previous in (None, "breach", "clear"):
        assert not _step(CLEAR, previous)[0]
        assert not _step(UNDECIDED, previous)[0]


def test_a_synthetic_breach_never_fires() -> None:
    synthetic = EvalResult(True, True, "passed", synthetic=True)
    assert not _step(synthetic, "clear")[0]


def test_the_check_is_the_monitor_id() -> None:
    _, policy = _step(CLEAR, None)
    expression, context = policy.calls[0]
    assert expression == "below(x)" and context.check_id == "MON-04"
