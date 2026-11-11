"""Request dependencies: the acting person and the platform services (007 research R-01, R-02).

Services are built once, on first use, so the API starts without querying the data store. The API
never advances runs: the orchestrator worker does. It gets stub agent and reviewer objects only to
satisfy the engine's constructor.
"""

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from opentelemetry import trace
from sqlalchemy import Engine

from adlc.api.auth import current_person
from adlc.config.settings import Settings
from adlc.identity.protocol import Person
from adlc.ledger.service import LedgerService
from adlc.ledger.storage import FileStore, LedgerContentStore
from adlc.orchestration.engine import EngineConfig, PostgresTerminalRun
from adlc.orchestration.interfaces import Clock, SystemClock
from adlc.orchestration.service import Actor, OrchestratorService
from adlc.orchestration.stubs import StubAgent, StubReviewer
from adlc.policy.directory import AccountFileDirectory
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry

if TYPE_CHECKING:
    from adlc.inbox.service import InboxService


@dataclass
class Services:
    settings: Settings
    engine: Engine
    clock: Clock = field(default_factory=SystemClock)  # tests share the harness clock

    @cached_property
    def runs(self) -> PostgresTerminalRun:
        registry = SqlSpecRegistry(self.engine)
        clock = self.clock
        policy = build_policy_engine(
            self.engine,
            registry,
            clock,
            synthetic_dir=self.settings.synthetic_dir,
            directory=AccountFileDirectory(
                self.settings.accounts_file, self.settings.role_catalogue, self.settings.env
            ),
        )
        return PostgresTerminalRun(
            self.engine, registry, policy, StubAgent(), StubReviewer(), clock, EngineConfig()
        )

    @cached_property
    def orchestration(self) -> OrchestratorService:
        return OrchestratorService(self.runs, self.settings.deadletter_role or "")

    @cached_property
    def inbox(self) -> "InboxService":
        from adlc.inbox.service import InboxService  # noqa: PLC0415 - avoids an import cycle

        return InboxService(
            self.runs, self.ledger, self.settings.deadletter_role, self.settings.spec_dir
        )

    @cached_property
    def ledger(self) -> LedgerService:
        files = FileStore(
            self.settings.file_store_dir,
            max_bytes=self.settings.attachment_max,
            allowed_types=self.settings.attachment_types,
        )
        return LedgerService(self.runs, LedgerContentStore(files))


def services(request: Request) -> Services:
    built: Services = request.app.state.services
    return built


def current_actor(person: Annotated[Person, Depends(current_person)]) -> Actor:
    """The signed-in person as the acting actor; the account is added to the request's span."""
    trace.get_current_span().set_attribute("account", person.account_name)
    return Actor.from_person(person)


def traced(*, run_id: str | None = None, usecase_id: str | None = None) -> None:
    span = trace.get_current_span()
    if run_id:
        span.set_attribute("run_id", run_id)
    if usecase_id:
        span.set_attribute("usecase_id", usecase_id)


ActorDep = Annotated[Actor, Depends(current_actor)]
ServicesDep = Annotated[Services, Depends(services)]
