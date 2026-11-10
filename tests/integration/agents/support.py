"""Shared constants and helpers for the 006 runtime integration tests."""

import json
from collections.abc import Mapping
from typing import Any

from adlc.agents.catalogue import AgentCatalogue, ModelCatalogue, load_catalogues
from adlc.agents.fake import FakeGateway
from adlc.agents.store import SqlCallRecorder
from adlc.policy.synthetic import load_synthetic_artifacts
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry
from tests.support.orchestration import SPECS, SYNTHETIC, harness
from tests.support.pg import PlatformDatabase

BUNDLE = load_bundle(SPECS)
MODELS, AGENTS = load_catalogues(InMemorySpecRegistry.from_bundle(BUNDLE), "default")
PRIMARY = MODELS.entries("reasoning")[0].model
T1_AGENT = "t1-requirements-agent"
GOOD = json.dumps({"artifacts": load_synthetic_artifacts(SYNTHETIC)["T1"]})
BAD = json.dumps({"artifacts": {"kpis": [{"kpi": "x"}]}})


def _model_t1() -> AgentCatalogue:
    content = BUNDLE.catalogue_data("agents")
    agents = []
    for a in content["agents"]:
        if a["id"] == T1_AGENT:
            a = {
                **a,
                "implementation": "model",
                "prompt": {"id": "common-terminal-reviewer", "version": "1.0.0"},
            }
        agents.append(a)
    return AgentCatalogue.from_content({"agents": agents})


def _gateway(
    h_engine: Any, script: Mapping[str, Any], catalogue: ModelCatalogue = MODELS
) -> FakeGateway:
    return FakeGateway(catalogue, script, recorder=SqlCallRecorder(h_engine))


def _run(db: PlatformDatabase, script: Mapping[str, Any], **kwargs: Any) -> Any:
    """A harness whose T1 agent is a model agent answered by ``script``."""

    class Late:
        """The gateway needs the harness engine; bind it once the harness exists."""

        gateway: FakeGateway | None = None

        def complete(self, request: Any) -> Any:
            assert self.gateway is not None
            return self.gateway.complete(request)

    late = Late()
    ctx = harness(db, gateway=late, agents=_model_t1(), **kwargs)
    h = ctx.__enter__()
    late.gateway = _gateway(h.app, script)
    return ctx, h, late
