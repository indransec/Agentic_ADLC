"""T016: tests that are not litellm_contract cannot reach LiteLLM (no network in tests)."""

from decimal import Decimal

import pytest

from adlc.agents.catalogue import ModelEntry
from adlc.agents.gateway import LiteLLMTransport


def test_litellm_is_blocked_outside_contract_tests() -> None:
    entry = ModelEntry("openai", "openai/gpt-4o-mini", Decimal(1), Decimal(1), 10, 100, "internal")
    with pytest.raises(RuntimeError, match="blocked in tests"):
        LiteLLMTransport().call(entry, [{"role": "user", "content": "hi"}], 5, 1.0, "k")
