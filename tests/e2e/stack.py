"""022 T027: a deterministic platform for the browser end-to-end tests (Playwright).

``uv run python -m tests.e2e.stack --ui-port 8611 --api-port 8612 --state web/e2e/.stack.json``

A fresh harness database (the real adlc-specs registered, stub agents and reviewer: no model is
ever called), seeded with known runs, behind the real platform API and the real ``adlc-web``
serving ``web/dist``. A drain loop moves the orchestrator on, as the orchestrator process would.
The state file (seeded ids, accounts, password, both URLs) is written last, once both servers
answer; Playwright waits for ``/health`` on the ui port. SIGTERM or SIGINT stops everything.
"""

import argparse
import json
import signal
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import uvicorn
from openpyxl import Workbook
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from adlc.api.app import create_app
from adlc.config.settings import UiSettings
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import Clarification
from adlc.web.server import create_app as create_web
from tests.integration.conftest import settings_for
from tests.support.api import PASSWORD, write_accounts
from tests.support.db import REPO_ROOT, PlatformDatabase
from tests.support.lifecycle import walk_to
from tests.support.orchestration import (
    DEADLETTER_ROLE,
    SPECS,
    SYNTHETIC,
    Harness,
    build_template,
    harness,
    person,
)

DIST = REPO_ROOT / "web" / "dist"
TABLE = "functional_requirements"  # a T1 artifact in adlc-specs (editable at sign-off)
SHEET_TABLE = "non_functional_requirements"
# 022 T067: markup and script that every page must show as text (no "/" in the file name: the
# platform keeps only a name's last path segment)
SCRIPT = "<script>window.__pwned=1</script><b>bold</b>[click](http://evil.example)"
FILE_NAME = "<img src=x onerror=window.__pwned=1>[c](javascript:x).md"


def requirements(count: int) -> list[dict[str, Any]]:
    return [
        {
            "req_id": f"FR-{i:04d}",
            "description": f"Requirement {i}",
            "priority": "must",
            "persona": "handler",
            "acceptance_criteria": f"FR-{i:04d} passes its test",
        }
        for i in range(1, count + 1)
    ]


def spreadsheet(path: Path, artifact: str, rows: list[dict[str, Any]]) -> Path:
    """An .xlsx of ``rows`` (sheet named after the artifact), with one value changed."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = artifact
    columns = list(rows[0])
    sheet.append(columns)
    for index, row in enumerate(rows):
        values = [row.get(c) for c in columns]
        if index == 0:
            values[columns.index("requirement")] = "p95 latency (from the spreadsheet)"
        sheet.append(values)
    book.save(path)
    return path


def seed(h: Harness, ledger: Any, work: Path) -> dict[str, Any]:
    """Known states for the end-to-end tests (more are added as stories need them).

    The escalation is seeded first: it moves the harness clock past T1's escalation timer, and
    runs opened afterwards are due from the new time.
    """
    _, escalated_run = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))
    h.drain()
    usecase, sign_off_run = walk_to(h, "T1")  # deep links (session), then passed (sign-off)
    _, rework_run = walk_to(h, "T1")  # sent to rework (sign-off)
    _, stale_run = walk_to(h, "T1")  # changed behind the page (stale)
    owner = person("product_owner")
    _, large_run = walk_to(h, "T1")  # 1,000 rows: editable in the page
    _, larger_run = walk_to(h, "T1")  # 1,001 rows: read-only, upload offered
    _, sheet_run = walk_to(h, "T1")  # a spreadsheet replaces a table
    for run, count in ((large_run, 1000), (larger_run, 1001)):
        ledger.edit_artifact(owner, run, TABLE, requirements(count))
    h.drain()
    sheet_rows = h.run(sheet_run).artifacts[SHEET_TABLE]
    h.agent.script = {"T2": {1: Clarification(("Which channels are in scope?",))}}
    _, clarification_run = walk_to(h, "T2")
    h.agent.script = {}
    _, waiver_run = walk_to(h, "T1")
    h.service.decide(
        person("business_owner"),
        waiver_run,
        "exception",
        reason="accepted with a control",
        fields={
            "waiver_owner": "product_owner-person",
            "expiry": "2099-01-01",
            "compensating_control": "weekly manual review",
            "risk_acceptance": "accepted for the pilot only",
        },
    )
    h.drain()
    hostile = hostile_seeds(h, ledger, owner)
    _, keyboard_run = walk_to(h, "T1")  # passed with the keyboard only (a11y)
    dead_usecase = h.submit("Dead letter case")
    with h.owner.begin() as conn:  # one event, dead-lettered as the router would after its retries
        dead_letter = conn.execute(
            text(
                "UPDATE outbox_event SET dead_lettered_at = now(), attempts = 5, "
                "last_error = 'route failed: subscriber unavailable' WHERE event_id = ("
                "SELECT event_id FROM outbox_event WHERE event_type = 'usecase.submitted' "
                "AND json_extract(payload, '$.usecase_id') = :u) RETURNING event_id"
            ),
            {"u": dead_usecase},
        ).scalar_one()
    return {
        "usecase": usecase,
        "sign_off_run": sign_off_run,
        "rework_run": rework_run,
        "stale_run": stale_run,
        "large_run": large_run,
        "larger_run": larger_run,
        "sheet_run": sheet_run,
        "escalated_run": escalated_run,
        "clarification_run": clarification_run,
        "clarification": f"{clarification_run}/clar-1",
        "waiver_run": waiver_run,
        "waiver": h.run(waiver_run).pending_waiver_id,
        "dead_letter": str(dead_letter),
        "keyboard_run": keyboard_run,
        "script": SCRIPT,
        "file_name": FILE_NAME,
        **hostile,
        "table": TABLE,
        "sheet_table": SHEET_TABLE,
        "spreadsheet": str(spreadsheet(work / f"{SHEET_TABLE}.xlsx", SHEET_TABLE, sheet_rows)),
    }


def hostile_seeds(h: Harness, ledger: Any, owner: Any) -> dict[str, Any]:
    """Person- and agent-written text with markup in every kind of field (022 T067, P-13)."""
    usecase = h.submit(f"{SCRIPT[:60]} case", " ".join([SCRIPT] * 4))
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    run = h.active(usecase, "T1").run_id
    rows = requirements(3)
    rows[0]["description"] = SCRIPT
    ledger.edit_artifact(owner, run, TABLE, rows)
    ledger.attach_file(owner, run, TABLE, b"<svg/>", FILE_NAME, "image/svg+xml")
    h.drain()
    detail = h.run(run)
    spec = h.orch.runs.entry(detail.terminal_id, detail.spec_version).spec
    causes = [c for c in spec_view.rework_causes(spec)]
    h.service.decide(
        owner,
        run,
        "rework",
        comment=SCRIPT,
        root_cause=causes[0],
        reason=SCRIPT,
        fields={"owner_comment": SCRIPT},
    )
    h.drain()
    reworked = [r.run_id for r in h.runs(usecase) if r.terminal_id == "T1" and r.run_id != run]
    # the stub agent counts builds per terminal across runs: script this use case's T2 build
    h.agent.script = {"T2": {h.agent.calls["T2"] + 1: Clarification((SCRIPT,))}}
    _, asked = walk_to(h, "T2")
    h.agent.script = {}
    return {
        "hostile_usecase": usecase,
        "hostile_run": run,
        "hostile_reworked_run": reworked[0] if reworked else None,
        "hostile_clarification_run": asked,
        "hostile_clarification": f"{asked}/clar-1",
    }


def serve(app: Any, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError(f"server on :{port} did not start")
        time.sleep(0.05)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tests.e2e.stack", description=__doc__)
    parser.add_argument("--ui-port", type=int, default=8611)
    parser.add_argument("--api-port", type=int, default=8612)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args(argv)
    if not (DIST / "index.html").is_file():
        raise SystemExit("web/dist is missing: run `make web-build` first")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    with tempfile.TemporaryDirectory(prefix="adlc-e2e-") as folder:
        work = Path(folder)
        template = build_template(PlatformDatabase(work / "template.db"))
        with harness(template) as h:
            accounts = write_accounts(work / "accounts.yaml")
            settings = settings_for(
                h.db,
                accounts,
                deadletter_role=DEADLETTER_ROLE,
                synthetic_dir=SYNTHETIC,
                spec_dir=SPECS,
                file_store_dir=work / "files",
            )
            api = create_app(settings, InMemorySpanExporter())  # no trace collector here
            api.state.services.clock = h.clock  # one clock for the API and the drain loop
            seeded = seed(h, api.state.services.ledger, work)
            api_url = f"http://127.0.0.1:{args.api_port}"
            web = create_web(
                UiSettings.model_validate(
                    {
                        "api_url": api_url,
                        "ui_dist_dir": DIST,
                        "env": "dev",
                        "ui_dashboard_refresh": "2s",
                    }
                )
            )
            servers = [serve(api, args.api_port), serve(web, args.ui_port)]
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text(
                json.dumps(
                    {
                        "base_url": f"http://127.0.0.1:{args.ui_port}",
                        "api_url": api_url,
                        "password": PASSWORD,
                        **seeded,
                    },
                    indent=2,
                )
            )
            while not stop.is_set():
                h.drain()
                stop.wait(0.3)
            for server in servers:
                server.should_exit = True
            api.state.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
