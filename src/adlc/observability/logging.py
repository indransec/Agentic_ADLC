"""Logging setup (constitution X, XI; FR-015).

Plain stdlib logging. The format never includes request headers, and a filter strips record
attributes whose names suggest credentials, so a stray ``extra=`` cannot leak them.
"""

import logging
import sys

SENSITIVE_ATTRIBUTES = frozenset({"authorization", "password", "token", "credential_hash"})
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class SensitiveAttributeFilter(logging.Filter):
    """Removes credential-like attributes from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name in SENSITIVE_ATTRIBUTES & set(vars(record)):
            delattr(record, name)
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SensitiveAttributeFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's access log prints the request line only (no headers); keep it.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
