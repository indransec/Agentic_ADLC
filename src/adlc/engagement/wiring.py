"""Builds the engagement layer from its settings (research R-02, R-15).

The board process and the API build it the same way: the platform's services (the same wiring as
the API, ``adlc.api.deps.Services``), the ADO adapter, the mapping, the board identities, the
projector, inbound sync and the reconciler.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from adlc.api.deps import Services
from adlc.config.settings import BoardSettings
from adlc.db.engine import open_engine
from adlc.engagement.ado import AdoBoard
from adlc.engagement.identities import BoardIdentities
from adlc.engagement.inbound import InboundSync
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.port import BoardAdapter
from adlc.engagement.projector import Projector
from adlc.engagement.reconcile import Reconciler
from adlc.identity.catalogue import load_role_ids
from adlc.orchestration.interfaces import Clock, SystemClock


class BoardDisabled(Exception):
    """``ADLC_BOARD_ENABLED`` is not true: nothing to sync with."""


@dataclass
class Engagement:
    settings: BoardSettings
    services: Services
    board: BoardAdapter
    mapping: TrackerMapping
    identities: BoardIdentities
    projector: Projector
    inbound: InboundSync
    reconciler: Reconciler

    @property
    def engine(self) -> Engine:
        return self.services.engine


def ado_board(settings: BoardSettings) -> AdoBoard:
    if not settings.board_enabled or settings.board_token is None:
        raise BoardDisabled("board sync is disabled (ADLC_BOARD_ENABLED is not true)")
    return AdoBoard(
        base_url=str(settings.board_url),
        organization=str(settings.board_organization),
        project=str(settings.board_project),
        token=settings.board_token.get_secret_value(),
        identities_url=settings.identities_url(),
        public_url=settings.public_url(),
    )


def build(
    settings: BoardSettings,
    *,
    services: Services | None = None,
    board: BoardAdapter | None = None,
    clock: Clock | None = None,
) -> Engagement:
    """``services``: reuse the API's; ``board``: a stand-in (tests); else from settings."""
    clock = clock or (services.clock if services is not None else SystemClock())
    services = services or Services(settings, open_engine(settings), clock)
    board = board or ado_board(settings)
    mapping = TrackerMapping.load(settings.board_mapping_file)
    identities = BoardIdentities.load(
        settings.accounts_file,
        load_role_ids(settings.role_catalogue),
        settings.env,
        str(settings.board_service_identity),
    )
    projector = Projector(
        services.engine,
        services.inbox,
        board,
        mapping,
        str(settings.board_evidence_url),
        clock,
        settings.time_scale,
    )
    inbound = InboundSync(
        services.engine,
        services.orchestration,
        board,
        mapping,
        identities,
        projector,
        clock,
        settings.board_start_from,
    )
    reconciler = Reconciler(
        services.engine, projector, board, mapping, clock, settings.deadletter_role
    )
    return Engagement(
        settings, services, board, mapping, identities, projector, inbound, reconciler
    )
