"""013 T022 (FR-008, FR-009; SC-004, SC-005): every dashboard route needs a session; any signed-in
role reads any use case; a 50-run journey answers in under 2 s."""

import time
from datetime import timedelta

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

ROUTES = (
    "/dashboard/usecases/UC-0001/journey",
    "/dashboard/usecases/UC-0001/kpis",
    "/dashboard/activity",
    "/dashboard/runs/UC-0001/T0/run-1/timeline",
    "/dashboard/portfolio",
)


def test_session_required_and_open_to_every_role(h: Harness, api: Api) -> None:
    walk_to(h, "T2")
    for route in ROUTES:
        assert api.client.get(route).status_code == 401, route
        answer = api.get("data_owner", route)  # a role with no part in this use case
        assert answer.status_code == 200, (route, answer.text)
    assert api.get("sre", "/dashboard/usecases/UC-9999/journey").status_code == 404
    assert api.get("sre", "/dashboard/runs/UC-9999/T0/run-1/timeline").status_code == 404


def test_a_fifty_run_journey_is_fast(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T8", tier="low")
    for _ in range(45):  # T8 review periods: one run each
        h.pass_run(h.active(usecase, "T8").run_id)
        h.clock.advance(timedelta(days=40))
        h.drain()
    runs = len(h.runs(usecase))
    assert runs >= 50, runs
    started = time.perf_counter()
    answer = api.get("sre", f"/dashboard/usecases/{usecase}/journey")
    elapsed = time.perf_counter() - started
    assert answer.status_code == 200 and elapsed < 2.0, elapsed
    lane = next(lane for lane in answer.json()["lanes"] if lane["terminal_id"] == "T8")
    assert len(lane["runs"]) == 20 and lane["runs"][0]["collapsed"]  # oldest periods collapsed
