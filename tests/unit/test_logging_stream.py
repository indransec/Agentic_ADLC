"""The platform's log handler writes to the stderr of the moment (found with 020's full test run:
016's CLI tests left the handler bound to a test runner's closed stream, and a later CLI's output
carried a logging error)."""

from __future__ import annotations

import io
import logging
import sys

import pytest

from adlc.observability.logging import configure_logging


def test_records_go_to_the_current_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    first = io.StringIO()
    monkeypatch.setattr(sys, "stderr", first)
    configure_logging("INFO")
    first.close()  # the stream the handler was configured with is gone
    second = io.StringIO()
    monkeypatch.setattr(sys, "stderr", second)
    logging.getLogger("adlc.test").warning("after the first stream closed")
    assert "after the first stream closed" in second.getvalue()
    assert "Logging error" not in second.getvalue()


def test_credentials_are_still_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    configure_logging("INFO")
    logging.getLogger("adlc.test").warning("plain", extra={"password": "secret-value"})
    assert "plain" in stream.getvalue()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None)
    record.token = "secret"
    handler = next(h for h in logging.getLogger().handlers if type(h).__name__ == "_AdlcHandler")
    assert handler.filter(record) and not hasattr(record, "token")
