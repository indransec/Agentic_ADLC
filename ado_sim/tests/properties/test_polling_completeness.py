"""SC-002: a poller that passes back the previous query's ``asOf`` misses no change (T044).

Four identities make 1,000 changes to 50 items in a background thread while a reader polls
every 50 ms with ``[System.ChangedDate] >= <asOf of its previous query>`` and reads each
returned item's updates. The reader must see every update exactly once (after de-duplication
by item and rev), in revision order per item, attributed to the identity that made it.

The writer's clock pauses after reading the time, inside its write transaction, as a slow
writer would: a reader whose bound came from its own clock instead of its snapshot then misses
changes that were stamped before the bound but committed after its query.
"""

from __future__ import annotations

import random
import threading
import time

from ado_sim.db import utc_now
from ado_sim.wiql import run_query
from ado_sim.workitems import WorkItemStore
from tests.conftest import title
from tests.properties.conftest import identities

ITEMS, CHANGES = 50, 1000
QUERY = (
    "SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '{since}'"
    " ORDER BY [System.ChangedDate] ASC, [System.Id] ASC"
)


def test_polling_sees_every_change_once_in_order(store: WorkItemStore) -> None:
    writers = identities(store.db)
    item_ids = [store.create("Task", [title(f"item {n}")], writers[0]).id for n in range(ITEMS)]
    made: dict[tuple[int, int], str] = {
        (item_id, 1): writers[0].unique_name for item_id in item_ids
    }
    failures: list[BaseException] = []

    def slow_clock() -> str:
        now = utc_now()
        time.sleep(0.001)
        return now

    writer_store = WorkItemStore(store.db, slow_clock)
    done = threading.Event()

    def write() -> None:
        chooser = random.Random(15)  # noqa: S311 - test data, not security
        try:
            for change in range(CHANGES):
                item_id = chooser.choice(item_ids)
                writer = writers[change % len(writers)]
                view = writer_store.update(item_id, [title(f"change {change}")], writer)
                made[(item_id, view.rev)] = writer.unique_name
        except BaseException as error:  # pragma: no cover - reported below
            failures.append(error)
        finally:
            done.set()

    seen: dict[tuple[int, int], str] = {}
    order: dict[int, list[int]] = {item_id: [] for item_id in item_ids}
    since = "2000-01-01T00:00:00Z"

    def poll() -> str:
        result = run_query(store.db, QUERY.format(since=since), time_precision=True)
        for item_id in result.work_items:
            for update in store.updates(item_id):
                key = (item_id, update.rev)
                if key not in seen:
                    seen[key] = update.revised_by["uniqueName"]
                    order[item_id].append(update.rev)
        return result.as_of

    thread = threading.Thread(target=write)
    thread.start()
    polls = 0
    while not done.is_set():
        since = poll()
        polls += 1
        time.sleep(0.05)
    thread.join()
    since = poll()

    assert not failures
    assert polls > 1, "the writer finished before the reader polled twice; nothing was raced"
    assert len(made) == ITEMS + CHANGES
    assert seen == made
    for item_id, revs in order.items():
        assert revs == sorted(revs) == list(range(1, len(revs) + 1)), item_id
