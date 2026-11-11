"""Retrieval records (008 research R-04, FR-021): every knowledge result returned to an agent is
written to ``run.knowledge_retrieval`` (append-only) with its own commit, before the model sees
it, so a citation can always be checked against what was read."""

from collections.abc import Sequence

from sqlalchemy import Engine, text

from adlc.agents.knowledge import Retrieval
from adlc.agents.tools import ToolContext
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.tracing import span

COLUMNS = "source, operation, request, document, section, content_hash, data_class, synthetic"


class SqlRetrievalLog:
    def __init__(self, engine: Engine, clock: Clock) -> None:
        self.engine, self.clock = engine, clock

    def record(self, context: ToolContext, found: Sequence[Retrieval]) -> list[Retrieval]:
        numbered: list[Retrieval] = []
        with (
            span("agent", "retrieval", run_id=context.run_id, terminal_id=context.terminal_id),
            self.engine.begin() as conn,
        ):
            for item in found:
                retrieval_id = conn.execute(
                    text(
                        "INSERT INTO run.knowledge_retrieval (run_id, attempt, step, source, "
                        "operation, request, document, section, content_hash, data_class, "
                        "synthetic, retrieved_at) VALUES (:run, :attempt, :step, :source, "
                        ":operation, :request, :document, :section, :hash, :class, :synthetic, "
                        ":at) RETURNING knowledge_retrieval_id"
                    ),
                    {
                        "run": context.run_id,
                        "attempt": context.attempt,
                        "step": context.step,
                        "source": item.source,
                        "operation": item.operation,
                        "request": item.request,
                        "document": item.document,
                        "section": item.section,
                        "hash": item.content_hash,
                        "class": item.data_class,
                        "synthetic": item.synthetic,
                        "at": self.clock.now(),
                    },
                ).scalar_one()
                numbered.append(item.with_id(int(retrieval_id)))
        return numbered

    def for_attempt(self, run_id: str, attempt: int) -> list[Retrieval]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT source, operation, request, document, section, content_hash, "
                    "data_class, synthetic, knowledge_retrieval_id FROM run.knowledge_retrieval "
                    "WHERE run_id = :r AND attempt = :a ORDER BY knowledge_retrieval_id"
                ),
                {"r": run_id, "a": attempt},
            ).mappings()
            return [
                Retrieval(
                    source=str(r["source"]),
                    operation=str(r["operation"]),
                    request=str(r["request"]),
                    document=str(r["document"]),
                    section=str(r["section"]),
                    content_hash=str(r["content_hash"]),
                    data_class=str(r["data_class"]),
                    synthetic=bool(r["synthetic"]),
                    retrieval_id=int(r["knowledge_retrieval_id"]),
                )
                for r in rows
            ]
