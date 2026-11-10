"""Runtime identifiers (SA Annex A.5) and time-ordered event ids (RFC 9562 UUID v7)."""

import os
import re
import threading
import time
import uuid

_RUN_ID = re.compile(r"^(?P<usecase>UC-[0-9]{4})/(?P<terminal>[A-Z][0-9]+)/run-(?P<k>[1-9][0-9]*)$")
_MAX_SEQUENCE = 9999


def _numbered(prefix: str, number: int) -> str:
    if not 1 <= number <= _MAX_SEQUENCE:
        raise ValueError(f"{prefix} number out of range: {number}")
    return f"{prefix}-{number:04d}"


def usecase_id(number: int) -> str:
    return _numbered("UC", number)


def waiver_id(number: int) -> str:
    return _numbered("WVR", number)


def run_id(usecase: str, terminal_id: str, run_number: int) -> str:
    return f"{usecase}/{terminal_id}/run-{run_number}"


def parse_run_id(value: str) -> tuple[str, str, int]:
    match = _RUN_ID.match(value)
    if match is None:
        raise ValueError(f"not a run id: {value!r}")
    return match["usecase"], match["terminal"], int(match["k"])


def clarification_id(run: str, round_number: int) -> str:
    return f"{run}/clar-{round_number}"


def correlation_id(usecase: str) -> str:
    return f"{usecase}/lifecycle"


_lock = threading.Lock()
_last = (0, 0)  # (unix_ms, 12-bit counter) of the previous id, for monotonic order


def uuid7(unix_ms: int | None = None) -> uuid.UUID:
    """UUID version 7: 48-bit Unix milliseconds, 12-bit counter, 62 random bits.

    The counter (RFC 9562 §6.2 method 1) keeps ids generated in the same millisecond in
    creation order, so outbox ids sort by creation time.
    """
    global _last
    with _lock:
        ms = int(time.time() * 1000) if unix_ms is None else unix_ms
        last_ms, counter = _last
        if ms <= last_ms and unix_ms is None:
            ms, counter = last_ms, counter + 1
            if counter > 0xFFF:
                ms, counter = last_ms + 1, 0
        else:
            counter = int.from_bytes(os.urandom(2), "big") & 0x3FF  # leave room to count up
        _last = (ms, counter)
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
