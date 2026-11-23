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
from pathlib import Path
from typing import Any

import uvicorn
from openpyxl import Workbook
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.api.app import create_app
from adlc.config.settings import UiSettings
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
    """Known states for the end-to-end tests (more are added as stories need them)."""
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
    return {
        "usecase": usecase,
        "sign_off_run": sign_off_run,
        "rework_run": rework_run,
        "stale_run": stale_run,
        "large_run": large_run,
        "larger_run": larger_run,
        "sheet_run": sheet_run,
        "table": TABLE,
        "sheet_table": SHEET_TABLE,
        "spreadsheet": str(spreadsheet(work / f"{SHEET_TABLE}.xlsx", SHEET_TABLE, sheet_rows)),
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
