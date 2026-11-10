"""Wiring the ledger service onto an orchestration test harness."""

from pathlib import Path

from adlc.config.settings import DEFAULT_ATTACHMENT_TYPES
from adlc.ledger.service import LedgerService
from adlc.ledger.storage import FileStore, LedgerContentStore
from tests.support.orchestration import Harness


def ledger_service(h: Harness, root: Path, max_bytes: int = 25_000_000) -> LedgerService:
    files = FileStore(root, max_bytes=max_bytes, allowed_types=DEFAULT_ATTACHMENT_TYPES)
    return LedgerService(h.orch.runs, LedgerContentStore(files))
