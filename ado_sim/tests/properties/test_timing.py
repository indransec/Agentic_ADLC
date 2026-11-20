"""SC-004: with 5,000 items, 95% of single-item reads, updates and supported queries finish
within 1 second (T046), measured through the HTTP API. The items are created in-process (faster);
the measured p95 of each operation is printed in the test summary."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import pytest

from ado_sim.workitems import WorkItemStore
from tests.conftest import OWNER, WIT, ApiClient, add, title
from tests.properties.conftest import identities, percentile

ITEMS, SAMPLES, LIMIT_SECONDS = 5000, 200, 1.0
AREAS = ("Agentic ADLC", "Agentic ADLC\\Use cases")
QUERIES = (
    "SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '{since}'"
    " ORDER BY [System.ChangedDate] ASC, [System.Id] ASC",
    "SELECT [System.Id], [System.Title] FROM workitems WHERE [System.WorkItemType] = 'Task'"
    " AND [System.AreaPath] UNDER 'Agentic ADLC\\Use cases' AND [System.State] <> 'Closed'",
    "SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @project"
    " AND [System.AssignedTo] = 'product.owner@adlc.demo' ORDER BY [System.Id] DESC",
    "SELECT [System.Id] FROM workitemLinks WHERE [Source].[System.WorkItemType] = 'Epic'"
    " AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward' MODE (MustContain)",
)


def _timed(action: Callable[[], object], count: int) -> list[float]:
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        action()
        samples.append(time.perf_counter() - started)
    return samples


# Coverage tracing slows Python several times over; SC-004 measures the simulator, not the tracer.
@pytest.mark.no_cover
def test_p95_within_one_second(
    store: WorkItemStore, api: ApiClient, measurements: dict[str, str]
) -> None:
    service, owner, *_ = identities(store.db)
    chooser = random.Random(4)  # noqa: S311 - test data, not security
    epics = [store.create("Epic", [title(f"use case {n}")], service).id for n in range(50)]
    for n in range(ITEMS - len(epics)):
        parent = epics[n % len(epics)]
        operations = [
            title(f"task {n}"),
            add("/fields/System.AreaPath", AREAS[n % 2]),
            add("/fields/System.AssignedTo", owner.unique_name if n % 3 == 0 else None),
            add(
                "/relations/-",
                {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"http://h/_apis/wit/workItems/{parent}",
                },
            ),
        ]
        store.create("Task", [op for op in operations if op["value"] is not None], service)
    since = store.get(ITEMS // 2).fields["System.ChangedDate"]

    def ok(response: Any) -> Any:
        assert response.status_code == 200, response.text
        return response

    def read() -> object:
        return ok(api.call("GET", f"{WIT}/workitems/{chooser.randint(1, ITEMS)}"))

    def update() -> object:
        return ok(api.patch(chooser.randint(1, ITEMS), [title(str(time.time()))], user=OWNER))

    def query() -> object:
        text = chooser.choice(QUERIES).format(since=since)
        return ok(
            api.call("POST", f"{WIT}/wiql", params={"timePrecision": "true"}, body={"query": text})
        )

    timings = {
        "read": _timed(read, SAMPLES),
        "update": _timed(update, SAMPLES),
        "query": _timed(query, SAMPLES // 4),
    }
    p95 = {name: percentile(samples, 0.95) for name, samples in timings.items()}
    measurements["SC-004 p95 with 5,000 items"] = ", ".join(
        f"{name} {seconds * 1000:.2f} ms" for name, seconds in p95.items()
    )
    assert all(seconds < LIMIT_SECONDS for seconds in p95.values()), p95
