"""``adlc-replay``: replays the reference use cases through the grounded terminals (008 T029).

``AgentReplies`` answers model calls per agent, in call order: the agent is recognised by its
registered system prompt, so a recording made live replays without a provider, whatever model the
catalogue lists. ``Replayer`` drives one reference use case through the platform services: it
submits it, lets the worker run, answers clarifications from the reference file, passes each
terminal with the approvers its sign-off rule needs, and stops at the review of the terminal the
reference names (``until``). Nothing here names a terminal, a role, an agent or a model.
"""

import json
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from ruamel.yaml import YAML
from sqlalchemy import Engine, text

from adlc.agents.catalogue import ModelCatalogue, ModelEntry
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import CallRecorder, Outcome, ProviderReply, Transport
from adlc.orchestration import routing, spec_view
from adlc.orchestration.engine import PostgresTerminalRun
from adlc.orchestration.service import Actor, OrchestratorService
from adlc.orchestration.states import RunState
from adlc.orchestration.store import RunRow

Planned = str | ProviderReply | Callable[[Sequence[Mapping[str, str]]], str | ProviderReply]
People = Callable[[str], Sequence[Actor]]  # every account holding the role, in order
SIGNATURE = 300  # characters of a system prompt that identify its agent
MAX_ROUNDS = 80
REPLAY_REASON = "replay: the approver continues to the next terminal"
ANY_ROLE = "any"  # reference answers used for a role with no prepared answer left

app = typer.Typer(help="Replay the reference use cases through the grounded terminals.")


# ------------------------------------------------------------------ replies


class AgentReplies:
    """Scripted or recorded replies per agent id; ``prompts`` maps agent ids to prompt bodies."""

    def __init__(
        self, prompts: Mapping[str, str], replies: Mapping[str, Sequence[Planned]]
    ) -> None:
        self.signatures = {aid: body.strip()[:SIGNATURE] for aid, body in prompts.items()}
        self.replies = {aid: list(r) for aid, r in replies.items()}
        self.used: dict[str, int] = defaultdict(int)
        self.calls: list[tuple[str, int]] = []

    def agent_of(self, messages: Sequence[Mapping[str, str]]) -> str | None:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        return next((aid for aid, sig in self.signatures.items() if system.startswith(sig)), None)

    def __call__(self, messages: Sequence[Mapping[str, str]]) -> ProviderReply:
        agent = self.agent_of(messages) or "?"
        planned = self.replies.get(agent) or []
        n = self.used[agent]
        self.used[agent] = n + 1
        self.calls.append((agent, n))
        if n >= len(planned):
            return reply("", outcome="request_error", reason=f"no reply {n + 1} for {agent}")
        item = planned[n]
        answer = item(messages) if callable(item) else item
        return answer if isinstance(answer, ProviderReply) else reply(answer, tokens=(400, 200))


def replay_gateway(
    catalogue: ModelCatalogue, replies: AgentReplies, recorder: CallRecorder | None = None
) -> FakeGateway:
    """The production gateway rules over ``replies``, whichever catalogue model is tried."""
    models = {e.model for entries in catalogue.tiers.values() for e in entries}
    return FakeGateway(catalogue, dict.fromkeys(models, replies), recorder=recorder)


def read_recording(folder: Path) -> dict[str, list[Planned]]:
    """``<folder>/<agent>.jsonl``: one reply per line, in call order."""
    found: dict[str, list[Planned]] = {}
    for path in sorted(folder.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        found[path.stem] = [
            reply(str(r["text"]), tokens=(int(r["tokens_in"]), int(r["tokens_out"]))) for r in rows
        ]
    return found


class RecordingTransport:
    """Wraps the live transport and keeps every usable answer per agent (no prompts, no keys)."""

    def __init__(self, inner: Transport, identify: AgentReplies) -> None:
        self.inner, self.identify = inner, identify
        self.sink: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def call(
        self,
        entry: ModelEntry,
        messages: Sequence[Mapping[str, str]],
        max_tokens: int,
        timeout_s: float,
        api_key: str,
    ) -> ProviderReply:
        result = self.inner.call(entry, messages, max_tokens, timeout_s, api_key)
        if result.outcome == Outcome.OK:
            agent = self.identify.agent_of(messages) or "unknown"
            self.sink[agent].append(
                {
                    "text": result.text,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                }
            )
        return result

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for agent, rows in self.sink.items():
            (folder / f"{agent}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.sink.clear()


# ------------------------------------------------------------------ references and results


@dataclass(frozen=True)
class Reference:
    id: str
    name: str
    intake_text: str
    until: str
    answers: Mapping[str, Sequence[str]]
    approver_fields: Mapping[str, Mapping[str, Any]]
    expected: Mapping[str, Any]


def load_references(folder: Path, only: Sequence[str] = ()) -> list[Reference]:
    references = []
    for path in sorted(folder.glob("*.yaml")):
        data = YAML(typ="safe").load(path.read_text())
        if only and data["id"] not in only:
            continue
        references.append(
            Reference(
                id=str(data["id"]),
                name=str(data["name"]),
                intake_text=str(data["intake_text"]),
                until=str(data["until"]),
                answers={
                    str(k): [str(a) for a in v] for k, v in (data.get("answers") or {}).items()
                },
                approver_fields=dict(data.get("approver_fields") or {}),
                expected=dict(data.get("expected") or {}),
            )
        )
    return references


@dataclass
class TerminalResult:
    terminal_id: str
    run_id: str
    state: str
    mandatory_missing: list[str]
    blocking_failed: list[str]
    first_attempt_clean: bool
    recommendation: str | None
    reason: str | None
    root_cause: str | None
    clarifications: int
    citations: int
    steps: int
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    agent: str | None
    agent_version: str | None
    prompt_hash: str | None
    playbook_hashes: dict[str, str]
    models: list[str]
    changed_from: str | None = None

    @property
    def ok(self) -> bool:
        return not self.mandatory_missing and not self.blocking_failed


@dataclass
class UseCaseResult:
    id: str
    usecase_id: str
    outcome: str  # "completed" or why it stopped
    expected_tier: str | None
    terminals: list[TerminalResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome == "completed" and all(t.ok for t in self.terminals)


# ------------------------------------------------------------------ driving one use case


class Replayer:
    def __init__(
        self,
        service: OrchestratorService,
        runs: PostgresTerminalRun,
        drain: Callable[[], int],
        people: People,
        max_rounds: int = MAX_ROUNDS,
    ) -> None:
        self.service, self.runs, self.drain, self.people = service, runs, drain, people
        self.max_rounds = max_rounds

    @property
    def engine(self) -> Engine:
        return self.runs.engine

    def run(self, ref: Reference) -> UseCaseResult:
        submitter = sorted(self.service.submitter_roles())[0]
        usecase = self.service.submit_usecase(self.people(submitter)[0], ref.name, ref.intake_text)
        result = UseCaseResult(ref.id, usecase, "stopped", ref.expected.get("risk_tier"))
        answers = {role: list(given) for role, given in ref.answers.items()}
        seen: dict[str, TerminalResult] = {}
        for _ in range(self.max_rounds):
            self.drain()
            active = [r for r in self.service.list_runs(usecase) if r.state != RunState.CLOSED]
            if not active:
                result.outcome = "stopped: no open run"
                break
            stop = self._step(ref, active, answers, seen)
            if stop is not None:
                result.outcome = stop
                break
        result.terminals = list(seen.values())
        return result

    def _step(
        self,
        ref: Reference,
        active: Sequence[RunRow],
        answers: dict[str, list[str]],
        seen: dict[str, TerminalResult],
    ) -> str | None:
        for run in active:
            if run.state == RunState.AWAITING_CLARIFICATION:
                if not self._answer(run, answers):
                    return "unanswered clarification"
            elif run.state == RunState.AWAITING_SIGN_OFF:
                seen[run.terminal_id] = self._result(run)
                if run.terminal_id == ref.until:
                    return "completed"
                self._pass(run, ref)
            elif run.state in (RunState.ESCALATED, RunState.BLOCKED):
                seen[run.terminal_id] = self._result(run)
                return f"stopped: {run.terminal_id} {run.state}"
        return None

    def _answer(self, run: RunRow, answers: dict[str, list[str]]) -> bool:
        with self.engine.connect() as conn:
            open_round = conn.execute(
                text(
                    "SELECT c.clarification_id, c.addressed_role, c.questions FROM "
                    "run.clarification_round c LEFT JOIN run.clarification_answer a "
                    "USING (clarification_id) WHERE c.run_id = :r AND a.clarification_id IS NULL"
                ),
                {"r": run.run_id},
            ).first()
        if open_round is None:
            return True
        role, questions = str(open_round[1]), list(open_round[2])
        given = answers.get(role) or []
        if given:
            reply_text = given.pop(0)
        elif answers.get(ANY_ROLE):
            reply_text = answers[ANY_ROLE][0]  # the reference's general answer, reused
        else:
            return False
        self.service.answer_clarification(
            self.people(role)[0], str(open_round[0]), [reply_text] * max(1, len(questions))
        )
        return True

    def _pass(self, run: RunRow, ref: Reference) -> None:
        spec = self.runs.entry(run.terminal_id, run.spec_version).spec
        typed = dict(ref.approver_fields.get(run.terminal_id) or {})
        missing = routing.emitted_values(spec, run.artifacts, {"usecase_id": run.usecase_id}, typed)
        typed.update({name: f"{name} (replay)" for name in missing.missing})
        recommended = (run.recommendation or {}).get("status")
        reason = None if recommended in (None, "pass") else REPLAY_REASON
        for _ in range(8):
            current = self.service.get_run(run.run_id)
            if current is None or current.state != RunState.AWAITING_SIGN_OFF:
                return
            with self.engine.connect() as conn:
                ctx = self.runs.context(conn, current)
            signed = {person for person, _ in ctx.approvals}
            needed = sorted(ctx.required_plus_roles - {r for _, r in ctx.approvals}) + sorted(
                ctx.rule_roles
            )
            # a person who has not approved yet: one account may hold several roles
            approver = next(
                (a for r in needed for a in self.people(r) if a.account_name not in signed), None
            )
            if approver is None:
                return
            self.service.decide(approver, run.run_id, "pass", reason=reason, fields=typed)

    def _result(self, run: RunRow) -> TerminalResult:
        spec = self.runs.entry(run.terminal_id, run.spec_version).spec
        mandatory = [a.id for a in spec_view.artifacts(spec) if a.condition is None]
        with self.engine.connect() as conn:
            attempts = conn.execute(
                text(
                    "SELECT agent_id, agent_version, prompt_hash, playbook_hashes, steps, "
                    "tokens_in, tokens_out, cost_usd FROM run.agent_attempt WHERE run_id = :r "
                    "AND kind = 'build' ORDER BY agent_attempt_id"
                ),
                {"r": run.run_id},
            ).all()
            models = conn.execute(
                text(
                    "SELECT DISTINCT model FROM run.model_call WHERE run_id = :r AND "
                    "outcome = 'ok' ORDER BY model"
                ),
                {"r": run.run_id},
            ).scalars()
            citations = conn.execute(
                text("SELECT count(*) FROM run.artifact_citation WHERE run_id = :r"),
                {"r": run.run_id},
            ).scalar_one()
            rounds = conn.execute(
                text("SELECT count(*) FROM run.clarification_round WHERE run_id = :r"),
                {"r": run.run_id},
            ).scalar_one()
        last = attempts[-1] if attempts else None
        costs = [a[7] for a in attempts]
        recommendation = run.recommendation or {}
        return TerminalResult(
            terminal_id=run.terminal_id,
            run_id=run.run_id,
            state=str(run.state),
            mandatory_missing=[a for a in mandatory if not run.artifacts.get(a)],
            blocking_failed=[
                str(c["id"])
                for c in run.control_results
                if c.get("blocking") and not c.get("passed")
            ],
            first_attempt_clean=run.auto_retries == 0 and run.run_number == 1,
            recommendation=recommendation.get("status"),
            reason=recommendation.get("reason"),
            root_cause=recommendation.get("root_cause"),
            clarifications=int(rounds),
            citations=int(citations),
            steps=sum(int(a[4]) for a in attempts),
            tokens_in=sum(int(a[5]) for a in attempts),
            tokens_out=sum(int(a[6]) for a in attempts),
            cost_usd=None if not costs or None in costs else float(sum(costs)),
            agent=None if last is None else str(last[0]),
            agent_version=None if last is None else str(last[1]),
            prompt_hash=None if last is None or last[2] is None else str(last[2]),
            playbook_hashes={} if last is None else dict(last[3]),
            models=[str(m) for m in models],
        )


# ------------------------------------------------------------------ report


@dataclass
class Report:
    mode: str
    profile: str | None
    usecases: list[UseCaseResult]
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def ok(self) -> bool:
        return bool(self.usecases) and all(u.ok for u in self.usecases)

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "profile": self.profile,
            "started_at": self.started_at,
            "ok": self.ok,
            "usecases": [
                {
                    **asdict(u),
                    "ok": u.ok,
                    "terminals": [{**asdict(t), "ok": t.ok} for t in u.terminals],
                }
                for u in self.usecases
            ],
        }


def mark_changes(report: Report, baseline: Mapping[str, Any]) -> None:
    """Note where the reviewer's recommendation differs from a baseline report."""
    before = {
        (u["id"], t["terminal_id"]): t.get("recommendation")
        for u in baseline.get("usecases") or []
        for t in u.get("terminals") or []
    }
    for usecase in report.usecases:
        for result in usecase.terminals:
            key = (usecase.id, result.terminal_id)
            if key in before and before[key] != result.recommendation:
                result.changed_from = before[key] or "none"


def markdown(report: Report) -> str:
    lines = [
        f"# Replay report ({report.mode}{', ' + report.profile if report.profile else ''})",
        "",
        f"Started {report.started_at}. Result: {'ok' if report.ok else 'NOT ok'}.",
    ]
    for u in report.usecases:
        lines += [
            "",
            f"## {u.id} ({u.usecase_id}): {u.outcome}",
            "",
            "| Terminal | Mandatory missing | Blocking failed | First attempt clean | "
            "Recommendation | Changed from | Clarifications | Citations | Cost USD |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for t in u.terminals:
            cost = "?" if t.cost_usd is None else f"{t.cost_usd:.4f}"
            lines.append(
                f"| {t.terminal_id} | {', '.join(t.mandatory_missing) or '-'} | "
                f"{', '.join(t.blocking_failed) or '-'} | {t.first_attempt_clean} | "
                f"{t.recommendation or '-'} | {t.changed_from or '-'} | {t.clarifications} | "
                f"{t.citations} | {cost} |"
            )
    return "\n".join(lines) + "\n"


def write_report(report: Report, out: Path, baseline: Path | None = None) -> Path:
    if baseline is not None:
        mark_changes(report, json.loads((baseline / "report.json").read_text()))
    folder = out / report.started_at.replace(":", "").replace("+", "_")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(report.to_json(), indent=1, default=str) + "\n")
    (folder / "report.md").write_text(markdown(report))
    return folder


# ------------------------------------------------------------------ command line


@app.command()
def main(
    reference_set: Annotated[Path, typer.Option("--set")] = Path("data/reference_usecases"),
    only: Annotated[list[str] | None, typer.Option("--only")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    record: Annotated[Path | None, typer.Option("--record")] = None,
    recording: Annotated[Path | None, typer.Option("--recording")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline")] = None,
    out: Annotated[Path, typer.Option("--out")] = Path("reports/replays"),
) -> None:
    """Replay the reference use cases and write report.json and report.md."""
    from adlc.agents.replay_cli import run_cli  # noqa: PLC0415 - heavy imports only when run

    if (profile is None) == (recording is None) or (record is not None and profile is None):
        print("adlc-replay: give --profile (optionally --record) or --recording", file=sys.stderr)
        raise typer.Exit(2)
    report = run_cli(
        reference_set, list(only or []), profile=profile, record=record, recording=recording
    )
    folder = write_report(report, out, baseline)
    print(f"adlc-replay: report written to {folder}")
    raise typer.Exit(0 if report.ok else 1)


__all__ = [
    "AgentReplies",
    "Planned",
    "RecordingTransport",
    "Reference",
    "Replayer",
    "Report",
    "TerminalResult",
    "UseCaseResult",
    "app",
    "load_references",
    "read_recording",
    "replay_gateway",
    "write_report",
]
