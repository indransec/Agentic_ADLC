"""Prod-sim traffic split (FR-011; research R-06): which package answers a request."""

import hashlib
from typing import Literal

Mode = Literal["shadow", "canary", "full"]


def bucket(request_id: str) -> float:
    """A stable number in [0, 1) for a request id (even across ids)."""
    digest = hashlib.sha256(f"split:{request_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def chooses_candidate(mode: Mode, share: float, request_id: str, has_candidate: bool) -> bool:
    """True when the candidate answers this request (shadow never returns the candidate)."""
    return has_candidate and mode == "canary" and bucket(request_id) < share
