"""Board adapters for the port contract suite (T010, T011; FR-025).

``board`` is parametrised over the in-memory ``FakeBoard`` and the ADO adapter against a simulator
started from this repository (``ado_sim/``) for the session: migrated, seeded from its demo seed,
with tokens issued for the service account and one demo user. The simulator is skipped, with the
reason, when ``uv`` is not installed.
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from adlc.engagement.fake import FakeBoard
from adlc.engagement.model import BoardType
from adlc.engagement.port import BoardAdapter

ROOT = Path(__file__).resolve().parents[3]
SIM = ROOT / "ado_sim"
ORG, PROJECT = "adlc-demo", "Agentic ADLC"
SERVICE, PERSON = "adlc-platform@adlc.demo", "product.owner@adlc.demo"
EPIC, TASK = "Epic", "Task"
TITLE, STATE, DECISION = "System.Title", "System.State", "Custom.AdlcDecision"
AREA = "Agentic ADLC\\Use cases"
EPIC_STATES = ("T0 Intake & Qualification", "T1 Requirements & Outcome", "Closed", "Removed")
AGILE = ("New", "Active", "Resolved", "Closed", "Removed")
FIELDS = frozenset({TITLE, STATE, DECISION, "System.Description", "Custom.AdlcComment"})


@dataclass
class Boards:
    """One board seen by the platform's service account and by a person."""

    service: BoardAdapter
    person: BoardAdapter
    with_bad_token: Callable[[], BoardAdapter]
    kind: str


def fake_process() -> dict[str, BoardType]:
    return {
        EPIC: BoardType(EPIC, EPIC_STATES, FIELDS),
        TASK: BoardType(TASK, AGILE, FIELDS),
    }


def _fake() -> Boards:
    board = FakeBoard(
        types=fake_process(),
        areas=frozenset({"Agentic ADLC", AREA}),
        identities={SERVICE: "ADLC Platform", PERSON: "Product Owner"},
        service_identity=SERVICE,
        state_field=STATE,
        initial_states={EPIC: EPIC_STATES[0], TASK: AGILE[0]},
    )

    def bad() -> BoardAdapter:
        return board.with_token_refused()

    return Boards(board, board.as_user(PERSON), bad, "fake")


@dataclass
class Simulator:
    url: str
    service_token: str
    person_token: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(args: list[str], env: dict[str, str]) -> str:
    done = subprocess.run(  # noqa: S603 - fixed command line
        ["uv", "run", "--project", str(SIM), "ado-sim", *args],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    return done.stdout


@pytest.fixture(scope="session")
def simulator(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Simulator]:
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed: the ADO simulator cannot be started")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV" and not k.startswith("ADLC_")}
    env.update(
        ADO_SIM_DB_PATH=str(tmp_path_factory.mktemp("ado_sim") / "sim.db"),
        ADO_SIM_TOKEN_KEY=secrets.token_urlsafe(40),
        ADO_SIM_PORT=str(port),
        ADO_SIM_SEED_FILE=str(SIM / "seed" / "demo.yaml"),
        ADO_SIM_LOG_LEVEL="WARNING",
    )
    _run(["migrate"], env)
    _run(["seed", "--file", env["ADO_SIM_SEED_FILE"]], env)
    service_token = _run(["token", "issue", SERVICE], env).strip().splitlines()[-1]
    person_token = _run(["token", "issue", PERSON], env).strip().splitlines()[-1]
    # Start the server binary itself (not the uv wrapper) so stopping it stops the server.
    server = subprocess.Popen(  # noqa: S603 - fixed command line
        [str(SIM / ".venv" / "bin" / "ado-sim"), "serve"],
        env=env,
        cwd=SIM,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=1) as answer:  # noqa: S310
                    if answer.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("the ADO simulator did not start")
        yield Simulator(url, service_token, person_token)
    finally:
        server.terminate()
        server.wait(timeout=10)


def _ado(sim: Simulator) -> Boards:
    from adlc.engagement.ado import AdoBoard

    def make(token: str) -> BoardAdapter:
        return AdoBoard(base_url=sim.url, organization=ORG, project=PROJECT, token=token)

    return Boards(make(sim.service_token), make(sim.person_token), lambda: make("x" * 52), "ado")


@pytest.fixture(params=["fake", pytest.param("ado", marks=pytest.mark.board_contract)])
def board(request: pytest.FixtureRequest) -> Boards:
    if request.param == "fake":
        return _fake()
    return _ado(request.getfixturevalue("simulator"))
