"""T039: synthetic evidence and artifacts (research R-05)."""

from pathlib import Path

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import CompositeEvidenceProvider, Evidence, InMemoryEvidenceProvider
from adlc.policy.synthetic import SyntheticEvidenceProvider, load_synthetic_artifacts

SYNTHETIC = Path(__file__).resolve().parents[3] / "data" / "synthetic"
CTX = EvalContext("T1", "x", "UC-0001/T1/run-1", "UC-0001")


def test_evidence_and_artifacts_load() -> None:
    provider = SyntheticEvidenceProvider.from_dir(SYNTHETIC)
    ci = provider.get("ci", CTX)
    assert isinstance(ci, Evidence) and ci.value["status"] == "green" and ci.synthetic
    artifacts = load_synthetic_artifacts(SYNTHETIC)
    assert sorted(artifacts) == [f"T{n}" for n in range(10)]
    assert len(artifacts["T4"]["test_case_results"]) >= 500


def test_hashes_agree_across_sources() -> None:
    evidence = SyntheticEvidenceProvider.from_dir(SYNTHETIC).sources
    package = load_synthetic_artifacts(SYNTHETIC)["T3"]["candidate_package"][0]["sha256"]
    assert evidence["env"]["test"]["deployed_hash"] == package
    assert evidence["env"]["prod"]["deployed_hash"] == package
    assert evidence["release"]["package_sha256"] == package
    assert load_synthetic_artifacts(SYNTHETIC)["T6"]["deployment_package"][0]["sha256"] == package


def test_disabled() -> None:
    assert load_synthetic_artifacts(None) == {}


def test_real_evidence_wins_and_synthetic_is_marked() -> None:
    real = InMemoryEvidenceProvider({"ci": {"status": "red"}})
    composite = CompositeEvidenceProvider(real, SyntheticEvidenceProvider.from_dir(SYNTHETIC))
    ci = composite.get("ci", CTX)
    assert isinstance(ci, Evidence) and ci.value == {"status": "red"} and not ci.synthetic
    sbom = composite.get("sbom", CTX)
    assert isinstance(sbom, Evidence) and sbom.synthetic
