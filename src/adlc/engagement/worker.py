"""``adlc-board run``: the board sync process (research R-02; FR-004, FR-010a, FR-022).

Disabled (the default): it serves ``/health`` as ``disabled`` and does nothing, so the platform and
``make up --wait`` are unaffected. Enabled: it checks the mapping against the board (and retries
while the board is unreachable; a mapping with gaps never syncs), finishes updates claimed before a
stop, then loops: inbound poll, then projection, every ``poll_interval``. ``/health`` answers 200
with ``ok``, ``degraded`` (board unreachable or token refused), ``mapping_invalid`` or ``starting``.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from adlc.engagement import store
from adlc.engagement.port import BoardAuthFailed, BoardError
from adlc.engagement.wiring import Engagement

log = logging.getLogger(__name__)


class BoardWorker:
    def __init__(self, engagement: Engagement, poll_interval: timedelta | None = None) -> None:
        self.engagement = engagement
        self.poll_interval = poll_interval or engagement.mapping.poll_interval
        self.status = "starting"
        self.ready = False
        self.gaps: list[str] = []

    def check(self) -> bool:
        """The mapping against the board (R-12); True when every name exists."""
        e = self.engagement
        try:
            gaps = e.mapping.check_against(e.board.check())
        except BoardAuthFailed as error:
            return self._not_ready("degraded", "auth_failed", str(error))
        except BoardError as error:
            return self._not_ready(
                "degraded", "board_unreachable", f"{type(error).__name__}: {error}"
            )
        self.gaps = gaps
        if gaps:
            for gap in gaps:
                log.error("tracker mapping: %s", gap)
            return self._not_ready("mapping_invalid", "mapping_invalid", "; ".join(gaps))
        self.ready = True
        self.status = "ok"
        recovered = e.inbound.recover()
        if recovered:
            log.info("board sync finished %d updates claimed before the last stop", recovered)
        return True

    def _not_ready(self, status: str, outcome: str, error: str) -> bool:
        self.status = status
        with self.engagement.engine.begin() as conn:
            store.record_poll(conn, outcome, error, self.engagement.projector.clock.now())
        return False

    def step(self) -> None:
        """One round: read the board's changes, then bring the board in step."""
        if not self.ready and not self.check():
            return
        result = self.engagement.inbound.poll()
        self.engagement.projector.run_once()
        self.status = "ok" if result.outcome == "ok" else "degraded"

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.step()
            except Exception:  # noqa: BLE001 - the loop survives; the next round retries
                log.exception("board sync round failed")
                self.status = "degraded"
            stop.wait(self.poll_interval.total_seconds())


def serve_health(port: int, status: Callable[[], dict[str, Any]]) -> ThreadingHTTPServer:
    """``GET /health`` with the process status (200 while the process runs)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the http.server interface
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # health probes are not worth a log line each

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104 - container port
    threading.Thread(target=server.serve_forever, name="board-health", daemon=True).start()
    return server
