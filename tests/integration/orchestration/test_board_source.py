"""016 T019: a board request's origin is recorded with the command; the inbox path is unchanged."""

import json

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

SOURCE = {"board_item": 41, "update": 3}


def _details(h: Harness, run_id: str) -> list[dict[str, object]]:
    rows = h.sql(
        "SELECT detail FROM run_activity WHERE run_id = :r ORDER BY run_activity_id", r=run_id
    )
    return [json.loads(row[0]) if isinstance(row[0], str) else dict(row[0]) for row in rows]


def test_submission_records_its_source_in_the_event(h: Harness) -> None:
    usecase = h.service.submit_usecase(
        person("business_owner"), "Board case", "x" * 250, source=SOURCE
    )
    rows = h.sql(
        "SELECT payload FROM outbox_event WHERE usecase_id = :u ORDER BY created_at", u=usecase
    )
    payload = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else dict(rows[0][0])
    assert payload["source"] == SOURCE


def test_decision_records_its_source_in_the_activity(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    h.service.decide(person("product_owner"), run_id, "pass", source=SOURCE)
    assert any(detail.get("source") == SOURCE for detail in _details(h, run_id))


def test_the_inbox_path_records_no_source(h: Harness) -> None:
    usecase = h.submit()
    _, run_id = walk_to(h, "T1")
    h.service.decide(person("product_owner"), run_id, "pass")
    assert not any("source" in detail for detail in _details(h, run_id))
    rows = h.sql("SELECT payload FROM outbox_event WHERE usecase_id = :u", u=usecase)
    assert all("source" not in (json.loads(r[0]) if isinstance(r[0], str) else r[0]) for r in rows)
