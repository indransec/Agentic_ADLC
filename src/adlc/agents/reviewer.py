"""The common reviewer behind feature 003's ``Reviewer`` (006 US3; FR-016 to FR-018).

The reviewer sees only the checklist, the artifacts, the control results, the evidence the
terminal's prerequisites name, and answers to its own questions. It never sees the builder's
prompt, messages or reasoning: its input is built from ``ReviewContext`` and the ledger alone.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from sqlalchemy import text

from adlc.agents.context import (
    RUNTIME_RULES,
    ContextPack,
    data_block,
    prerequisite_terminals,
    read_evidence,
    resolve_ceiling,
)
from adlc.agents.gateway import CallIds
from adlc.agents.limits import limits_for
from adlc.agents.output import REVIEW_STATUSES, parse_review
from adlc.agents.prompts import ChecklistItem
from adlc.agents.runner import LoopOutcome, RuntimeDeps, outcome_name, record_attempt, run_loop
from adlc.agents.telemetry import set_attributes
from adlc.ledger import store as ledger_store
from adlc.ledger.storage import structured_hash
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.interfaces import (
    AttemptFailed,
    BudgetExceeded,
    Recommendation,
    ReviewContext,
    Reviewer,
    ReviewResult,
)
from adlc.orchestration.tracing import span

REVIEWER_ASKS = "reviewer"


def _ids(catalogue: Any, list_key: str) -> set[str]:
    content = {} if catalogue is None else catalogue.content
    return {str(e["id"]) for e in content.get(list_key) or []}


def review_instruction(items: tuple[ChecklistItem, ...], root_causes: set[str]) -> str:
    listed = "\n".join(f"- {i.id}: {i.text}" for i in items)
    return (
        "Checklist items to score (0 to 3 each):\n"
        f"{listed}\n"
        f"Recommended status: one of {list(REVIEW_STATUSES)}.\n"
        f"Root causes for rework: {sorted(root_causes)}.\n"
        'Answer with {"scores": {...}, "findings": [...], "recommendation": {...}} '
        'or {"clarification": {...}}, as described in your instructions.'
    )


class RuntimeReviewer:
    """Model reviewer, or the stub reviewer when ``mode`` is ``stub`` (recorded either way)."""

    def __init__(self, deps: RuntimeDeps, stub: Reviewer, mode: str = "stub") -> None:
        self.deps = deps
        self.stub = stub
        self.mode = mode

    def review(self, context: ReviewContext) -> ReviewResult:
        deps = self.deps
        with deps.engine.connect() as conn:
            run = run_store.load_run(conn, context.run_id)
            if run is None:
                raise ValueError(f"unknown run {context.run_id}")
            attempt = 1 + int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM run.agent_attempt "
                        "WHERE run_id = :r AND kind = 'review'"
                    ),
                    {"r": context.run_id},
                ).scalar()
                or 0
            )
            entry = deps.registry.entry(context.terminal_id, run.spec_version)
            if entry is None:
                raise ValueError(f"spec {context.terminal_id}@{run.spec_version} not registered")
            spec = entry.spec
            evidence = read_evidence(conn, run.usecase_id, prerequisite_terminals(spec))
            # 008: the sources the builder cited are evidence, not its reasoning (SA 7.2 point 5)
            cited = [
                {k: c[k] for k in ("artifact_id", "row_index", "source", "document", "section")}
                for c in ledger_store.citations(conn, context.run_id)
            ]
            classes = deps.registry.catalogue("data_classes")
            ceiling = resolve_ceiling(
                conn, run.usecase_id, _ceiling(spec), {} if classes is None else classes.content
            )
        reviewer_id = str((spec_view.body(spec).get("actors") or {}).get("reviewer"))
        agent = deps.agents.agent(reviewer_id)
        checklist_ref = (spec_view.body(spec).get("controls") or {}).get("checklist") or {}
        items = deps.texts.checklist(
            str(checklist_ref.get("ref")), str(checklist_ref.get("version"))
        )
        items = tuple(i for i in items if i.id in context.checklist_items) or tuple(
            ChecklistItem(i, "") for i in context.checklist_items
        )
        answered = [
            {"questions": c.get("questions"), "answers": c.get("answers")}
            for c in context.clarifications
            if c.get("asked_by") == REVIEWER_ASKS and c.get("answers") is not None
        ]
        content: dict[str, Any] = {
            "reviewer": {"id": agent.id, "version": agent.version},
            "spec": {
                "terminal_id": context.terminal_id,
                "version": entry.version,
                "content_hash": entry.content_hash,
            },
            "checklist": [{"id": i.id, "text": i.text} for i in items],
            "artifacts": dict(context.artifacts),
            "control_results": [
                {k: c.get(k) for k in ("id", "passed", "blocking", "reason")}
                for c in context.control_results
            ],
            "evidence": evidence,
            "clarifications": answered,
        }
        if cited:
            content["citations"] = cited
        pack = ContextPack(content, structured_hash(content), {})
        started = deps.clock.now()
        ids = {
            "run_id": context.run_id,
            "usecase_id": run.usecase_id,
            "terminal_id": context.terminal_id,
        }
        stub_mode = self.mode != "model"
        recorded_agent = replace(agent, implementation="stub") if stub_mode else agent
        prompt = None if stub_mode or agent.prompt is None else deps.texts.prompt(*agent.prompt)
        with span("agent", "review", **ids) as s:
            if stub_mode:
                result: Any = self.stub.review(context)
                if isinstance(result, Recommendation):
                    result = replace(result, reviewer="stub")
                outcome = LoopOutcome(result=result)
            elif prompt is None:
                outcome = LoopOutcome(result=AttemptFailed(f"reviewer {agent.id} has no prompt"))
            else:
                root_causes = _ids(deps.registry.catalogue("root_causes"), "root_causes")
                role_ids = _ids(deps.registry.catalogue("roles"), "roles")
                item_ids = [i.id for i in items]
                user = "\n\n".join(
                    [
                        data_block("checklist", content["checklist"]),
                        data_block("artifacts", content["artifacts"]),
                        data_block("control_results", content["control_results"]),
                        data_block("evidence", content["evidence"]),
                        *([data_block("citations", cited)] if cited else []),
                        data_block("clarifications", content["clarifications"]),
                        review_instruction(items, root_causes),
                    ]
                )
                outcome = run_loop(
                    deps,
                    tier=agent.model_tier,
                    data_class=ceiling,
                    messages=(
                        {"role": "system", "content": f"{prompt.body.strip()}\n\n{RUNTIME_RULES}"},
                        {"role": "user", "content": user},
                    ),
                    ids=CallIds(
                        context.run_id,
                        run.usecase_id,
                        context.terminal_id,
                        agent.id,
                        f"{context.run_id}/review/{attempt}",
                    ),
                    prompt_hash=prompt.hash,
                    context_hash=pack.hash,
                    limits=limits_for(
                        deps.limits, deps.overrides, agent.model_tier, context.terminal_id
                    ),
                    parse=lambda raw: parse_review(raw, item_ids, root_causes, role_ids),
                )
            set_attributes(
                s,
                {
                    "kind": "review",
                    "agent_id": agent.id,
                    "agent_version": agent.version,
                    "implementation": recorded_agent.implementation,
                    "attempt": attempt,
                    "outcome": outcome_name(outcome.result),
                    "steps": outcome.steps,
                    "tokens_in": outcome.tokens_in,
                    "tokens_out": outcome.tokens_out,
                    "corrections": outcome.corrections,
                    "limit_reached": outcome.limit_reached,
                },
            )
        record_attempt(
            deps,
            run_id=context.run_id,
            kind="review",
            attempt=attempt,
            agent=recorded_agent,
            prompt=prompt,
            pack=pack,
            outcome=outcome,
            started_at=started,
        )
        return _review_result(outcome.result)


def _ceiling(spec: Mapping[str, Any]) -> str:
    access = (spec_view.body(spec).get("authorities") or {}).get("data_access") or {}
    return str(access.get("max_class") or "")


def _review_result(result: Any) -> ReviewResult:
    """A budget breach while reviewing is a failed review (the reviewer could not finish)."""
    if isinstance(result, BudgetExceeded):
        return AttemptFailed(f"reviewer limit reached: {result.detail}")
    return result  # type: ignore[no-any-return]
