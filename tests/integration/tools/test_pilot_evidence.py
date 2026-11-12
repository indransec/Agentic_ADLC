"""T016 (FR-009): T3's prerequisites "dev environment provisioned" and "template version pinned"
read the pilot through the bridge, so their decisions are not synthetic; without the bridge they
fall back to synthetic evidence, labelled synthetic. T7's deployed hash reads prod-sim."""

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import (
    ChainEvidenceProvider,
    CompositeEvidenceProvider,
    InMemoryEvidenceProvider,
)
from adlc.policy.pilot_evidence import PilotEvidence
from adlc.policy.predicates import load_all
from adlc.policy.store import MemorySink
from adlc.tools.client import McpClient
from tests.support.tools import KEY

from .conftest import Tools

SYNTHETIC = InMemoryEvidenceProvider(
    {"env": {"dev": {"provisioned": True}}, "template": {"version": "golden-template-1.4.2"}},
    synthetic=True,
)
CTX = EvalContext("T3", "PRE-T3-03", "UC-0001/T3/run-1", "UC-0001")


def engine(bridge_url: str | None) -> CelPolicyEngine:
    records = InMemoryEvidenceProvider({})
    if bridge_url is not None:
        pilot = PilotEvidence(McpClient({"bridge": bridge_url}, 10), KEY)
        provider = CompositeEvidenceProvider(ChainEvidenceProvider(records, pilot), SYNTHETIC)
    else:
        provider = CompositeEvidenceProvider(records, SYNTHETIC)
    return CelPolicyEngine(provider, load_all(), sink=MemorySink())


def test_prerequisites_read_the_pilot(tools: Tools) -> None:
    policy = engine(tools.bridge_url)
    provisioned = policy.evaluate("is_provisioned(env.dev)", CTX)
    pinned = policy.evaluate("is_pinned(template.version)", CTX)
    assert provisioned.passed and not provisioned.synthetic
    assert pinned.passed and not pinned.synthetic
    assert policy.evaluate('template.version == "incident-triage@1.0.0"', CTX).passed


def test_deployed_hash_and_running_package(tools: Tools) -> None:
    stable = tools.pilot.add_package()
    tools.pilot.hosts["prod-sim"].stable = stable
    tools.pilot.hosts["dev"].running = {"package_hash": stable, "replicas": [{"healthy": True}]}
    policy = engine(tools.bridge_url)
    result = policy.evaluate(f'env.prod.deployed_hash == "{stable}" && env.dev.healthy', CTX)
    assert result.passed and not result.synthetic


def test_without_the_bridge_synthetic_evidence_is_used_and_labelled(tools: Tools) -> None:
    for policy in (engine(None), engine("http://127.0.0.1:1")):  # not configured, not answering
        provisioned = policy.evaluate("is_provisioned(env.dev)", CTX)
        assert provisioned.passed and provisioned.synthetic
