"""Worker processes: a package extracted to a folder, served by uvicorn on 127.0.0.1 (R-03).

The worker imports the agent code from the package itself (``template/agent`` first on the path),
so what runs is what was built. Only ``PILOT_*`` settings and a minimal environment are passed on.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

START_TIMEOUT_S = 30.0
PASSED_ON = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Worker:
    id: str
    port: int
    process: subprocess.Popen[bytes]
    root: Path
    settings: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def healthy(self) -> bool:
        return self.health() is not None

    def health(self) -> dict[str, Any] | None:
        """The worker's own report (package, model in use, leak), or None when it is down."""
        if self.process.poll() is not None:
            return None
        try:
            reply = httpx.get(f"{self.url}/health", timeout=2)
        except httpx.HTTPError:
            return None
        if reply.status_code != 200:
            return None
        report: dict[str, Any] = reply.json()
        return report

    def metrics(self) -> dict[str, Any] | None:
        try:
            reply = httpx.get(f"{self.url}/metrics", timeout=5)
        except httpx.HTTPError:
            return None
        if reply.status_code != 200:
            return None
        report: dict[str, Any] = reply.json()
        return report

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def start_worker(
    worker_id: str,
    root: Path,
    package_hash: str,
    environment: str,
    settings: Mapping[str, str],
) -> Worker:
    env = {k: v for k, v in os.environ.items() if k in PASSED_ON or k.startswith("PILOT_")}
    env.update(
        {
            "PILOT_PACKAGE_ROOT": str(root),
            "PILOT_PACKAGE_HASH": package_hash,
            "PILOT_ENVIRONMENT": environment,
            "PYTHONPATH": str(root / "template" / "agent"),
        }
    )
    if "model_mode" in settings:
        env["PILOT_MODEL_MODE"] = settings["model_mode"]
    port = free_port()
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-m",
            "uvicorn",
            "triage_agent.app:factory",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=root,
    )
    worker = Worker(worker_id, port, process, root, dict(settings))
    deadline = time.monotonic() + START_TIMEOUT_S
    while not worker.healthy():
        if process.poll() is not None or time.monotonic() > deadline:
            worker.stop()
            raise RuntimeError(f"worker {worker_id} did not start")
        time.sleep(0.1)
    return worker
