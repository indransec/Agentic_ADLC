"""Synthetic evidence and artifacts (research R-05; clarification 2026-11-10).

Stand-ins until real agents (006) and evidence sources (009–012) exist. The evidence provider is
layered behind real evidence by ``CompositeEvidenceProvider``, which marks every value it supplies
as synthetic, so decisions that read it are labelled.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from adlc.policy.evidence import InMemoryEvidenceProvider

EVIDENCE_FILE = "evidence.yaml"
ARTIFACTS_DIR = "artifacts"


def _load(path: Path) -> Any:
    return YAML(typ="safe").load(path.read_text())


class SyntheticEvidenceProvider(InMemoryEvidenceProvider):
    @classmethod
    def from_dir(cls, folder: Path) -> "SyntheticEvidenceProvider":
        path = folder / EVIDENCE_FILE
        data = _load(path) if path.is_file() else {}
        return cls(data if isinstance(data, dict) else {}, synthetic=True)


def load_synthetic_artifacts(
    folder: Path | None,
) -> dict[str, Mapping[str, list[dict[str, Any]]]]:
    """Artifacts per terminal id (``T0`` … from ``artifacts/T0.yaml`` …); empty when disabled."""
    if folder is None:
        return {}
    out: dict[str, Mapping[str, list[dict[str, Any]]]] = {}
    for path in sorted((folder / ARTIFACTS_DIR).glob("*.yaml")):
        data = _load(path)
        if isinstance(data, dict):
            out[path.stem] = data
    return out
