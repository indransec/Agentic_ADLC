"""Helpers to walk a use case to a terminal with scripted passes."""

from tests.support.orchestration import Harness

ORDER = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]


def walk_to(h: Harness, terminal: str, tier: str = "medium") -> tuple[str, str]:
    """Submit a use case and pass every terminal before ``terminal``; return (use case, run)."""
    usecase = h.submit()
    for t in ORDER[: ORDER.index(terminal)]:
        h.pass_run(h.active(usecase, t).run_id, {"risk_tier": tier})
    return usecase, h.active(usecase, terminal).run_id
