"""022 T008 (N-08, research R-04): every answer the web application reads keeps its JSON.

The 25 routes that gain a response model are called on scripted harness walks, and each answer is
compared with a golden file recorded before any model existed. Ids, times and hashes are
normalised (times keep their format, floats keep their type); everything else (keys, nesting, types, values) must match
exactly, so a model that drops, renames or re-serialises a field fails here.

Record the goldens with ``pytest tests/integration/api/test_response_shapes.py --update-golden``.
"""

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from adlc.orchestration.interfaces import Clarification
from tests.integration.api.test_artifacts import xlsx
from tests.integration.api.test_changes_api import APPROVER, _raise
from tests.integration.api.test_dead_letters_admin import COE, _dead_letter
from tests.integration.api.test_proposed_events import OWNER, _propose
from tests.integration.api.test_requests import EXCEPTION
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

GOLDEN = Path(__file__).parent / "golden"
ARTIFACT = "kpis"  # a T1 artifact in adlc-specs (as in test_artifacts.py)

_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SHA = re.compile(r"\b[0-9a-f]{64}\b")


def normalise(value: Any) -> Any:
    """Times keep their format with digits zeroed; uuids, sha256 digests and floats become
    markers (a float that turns into an int, or a string, still fails)."""
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if isinstance(value, float):
        return "<float>"  # durations and costs follow the wall clock; the type is what matters
    if isinstance(value, str):
        value = _TIME.sub(lambda m: re.sub(r"\d", "0", m.group(0)), value)
        value = _UUID.sub("<uuid>", value)
        return _SHA.sub("<sha256>", value)
    return value


class Goldens:
    def __init__(self, update: bool) -> None:
        self.update = update

    def check(self, name: str, answer: Any, status: int = 200) -> Any:
        assert answer.status_code == status, (name, answer.status_code, answer.text)
        body = answer.json()
        path = GOLDEN / f"{name}.json"
        got = normalise(body)
        if self.update:
            GOLDEN.mkdir(exist_ok=True)
            path.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
        else:
            assert path.exists(), f"missing golden {path.name}: run with --update-golden"
            assert got == json.loads(path.read_text()), name
        return body


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Goldens:
    return Goldens(bool(request.config.getoption("--update-golden")))


def version(api: Api, run: str) -> int:
    return int(api.get("sre", f"/runs/{run}").json()["run"]["version"])


def test_use_case_run_artifacts_and_dashboard(h: Harness, api: Api, golden: Goldens) -> None:
    created = golden.check(
        "usecases-create",
        api.post(
            "business_owner",
            "/usecases",
            json={"name": "Claims triage", "intake_text": "x" * 250},
        ),
        status=201,
    )
    usecase = created["usecase_id"]
    h.drain()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    run = h.active(usecase, "T1").run_id
    golden.check("usecases-list", api.get("business_owner", "/usecases"))
    golden.check("usecases-detail", api.get("business_owner", f"/usecases/{usecase}"))
    golden.check("runs-detail", api.get("product_owner", f"/runs/{run}"))

    rows = api.get("product_owner", f"/runs/{run}").json()
    kpis = next(a for a in rows["artifacts"] if a["id"] == ARTIFACT)["rows"]
    golden.check(
        "artifacts-save",
        api.put(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}",
            json={
                "rows": [{**kpis[0], "target": 99}, *kpis[1:]],
                "expected_version": version(api, run),
            },
        ),
    )
    h.drain()
    columns = list(kpis[0])
    sheet = xlsx([columns, *[[row.get(c) for c in columns] for row in kpis]])
    golden.check(
        "artifacts-spreadsheet",
        api.post(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}/spreadsheet",
            files={"file": ("kpis.xlsx", sheet, "application/octet-stream")},
            data={"expected_version": str(version(api, run))},
        ),
    )
    h.drain()
    golden.check(
        "artifacts-attach",
        api.post(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
            files={"file": ("kpi notes.md", b"# KPI source", "text/markdown")},
            data={"expected_version": str(version(api, run))},
        ),
    )
    golden.check("artifacts-history", api.get("sre", f"/runs/{run}/artifacts/{ARTIFACT}/history"))
    h.drain()
    golden.check("inbox", api.get("product_owner", "/inbox"))
    form = api.get("product_owner", f"/runs/{run}").json()["form"]
    golden.check(
        "runs-decision",
        api.post(
            "product_owner",
            f"/runs/{run}/decisions",
            json={
                "decision": "rework",
                "comment": "the KPI baseline is missing",
                "reason": "the baseline must come first",
                "root_cause": form["root_causes"][0],
                "expected_version": version(api, run),
                "fields": {},
            },
        ),
    )
    h.drain()
    golden.check("usecases-verify", api.post("sre", f"/usecases/{usecase}/verify"))
    golden.check("dashboard-journey", api.get("sre", f"/dashboard/usecases/{usecase}/journey"))
    golden.check("dashboard-kpis", api.get("sre", f"/dashboard/usecases/{usecase}/kpis"))
    golden.check("dashboard-portfolio", api.get("sre", "/dashboard/portfolio"))
    golden.check(
        "dashboard-activity", api.get("sre", "/dashboard/activity", params={"usecase_id": usecase})
    )
    golden.check("dashboard-timeline", api.get("sre", f"/dashboard/runs/{run}/timeline"))


def test_clarification_answer(h: Harness, api: Api, golden: Goldens) -> None:
    h.agent.script = {"T2": {1: Clarification(("Which channels are in scope?",))}}
    _, run = walk_to(h, "T2")
    path = f"/clarifications/{run}/clar-1/answers"
    golden.check(
        "clarification-answer", api.post("engineering_lead", path, json={"answers": ["web"]})
    )


def test_escalation_completion(h: Harness, api: Api, golden: Goldens) -> None:
    _, run = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))
    h.drain()
    golden.check(
        "runs-escalation",
        api.post(
            "product_owner",
            f"/runs/{run}/escalation",
            json={"artifacts": {}, "expected_version": version(api, run)},
        ),
    )


def test_waiver_decision(h: Harness, api: Api, golden: Goldens) -> None:
    _, run = walk_to(h, "T1")
    proposed = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={**EXCEPTION, "expected_version": version(api, run)},
    )
    assert proposed.status_code == 200, proposed.text
    waiver = h.run(run).pending_waiver_id
    golden.check(
        "waiver-decision",
        api.post(
            "product_owner", f"/waivers/{waiver}/decision", json={"approve": True, "comment": "ok"}
        ),
    )


def test_change_requests(h: Harness, api: Api, golden: Goldens) -> None:
    change = _raise(h)
    golden.check("changes-list", api.get(APPROVER, "/changes"))
    golden.check(
        "changes-decision",
        api.post(APPROVER, f"/changes/{change}/decision", json={"approve": True, "comment": "ok"}),
    )


def test_proposed_events(h: Harness, api: Api, golden: Goldens) -> None:
    _, run = walk_to(h, "T8")
    _propose(h, api, run, ("EV-1", "drift"))
    golden.check("events-proposed", api.get(OWNER, "/events/proposed"))
    golden.check(
        "events-decision",
        api.post(
            OWNER, f"/events/proposed/{run}/EV-1", json={"confirm": False, "comment": "known"}
        ),
    )


def test_dead_letters(h: Harness, api: Api, golden: Goldens) -> None:
    h.submit()
    _dead_letter(h)
    (dead,) = golden.check("dead-letters-list", api.get(COE, "/dead-letters"))
    golden.check("dead-letters-detail", api.get(COE, f"/dead-letters/{dead['event_id']}"))
