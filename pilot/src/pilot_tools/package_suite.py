"""The package suite CI runs on a built package (feature 011, research R-04), in its own process
under ``coverage`` so the agent's code is measured from import. It starts the package in-process,
answers smoke incidents and a scored golden subset, and reports counts and observed signals as
JSON on stdout. Run: ``python -m pilot_tools.package_suite <package root> <package hash>``.
"""

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pilot_tools.incidents import generate

SMOKE_SEED, SMOKE_SIZE = 1, 5
GOLDEN_SEED, GOLDEN_SIZE = 7, 20
RAI_COUNTERS = ("toxic_outputs", "pii_outputs", "jailbreak_attempts")
LABELS = ("expected", "planted_pii", "edge_case", "synthetic")


def run(root: Path, package_hash: str) -> dict[str, Any]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    from triage_agent.app import create_app  # noqa: PLC0415 - imported under coverage

    client = TestClient(create_app(root, package_hash))
    template = root / "template"
    total = passed = 0
    sample = ""
    for incident in generate(SMOKE_SEED, SMOKE_SIZE, template=template):
        total += 1
        answer = client.post("/triage", json={k: v for k, v in incident.items() if k not in LABELS})
        ok = answer.status_code == 200 and answer.json().get("package_hash") == package_hash
        passed += ok and bool(answer.json().get("team"))
        sample = sample or str(incident["incident_id"])
    for incident in generate(GOLDEN_SEED, GOLDEN_SIZE, template=template):
        total += 1
        answer = client.post("/triage", json={k: v for k, v in incident.items() if k not in LABELS})
        passed += (
            answer.status_code == 200 and answer.json().get("team") == incident["expected"]["team"]
        )
    counts = client.get("/metrics").json().get("counts") or {}
    names = {s.name for s in exporter.get_finished_spans()}
    return {
        "total_count": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "observability": [
            {
                "signal": "traces",
                "emitting": {"triage.request", "triage.tool"} <= names,
                "sample_trace_id": sample,
            },
            {
                "signal": "rai_metrics",
                "emitting": all(k in counts for k in RAI_COUNTERS),
                "sample_trace_id": sample,
            },
        ],
    }


def main() -> None:
    print(json.dumps(run(Path(sys.argv[1]), sys.argv[2])))


if __name__ == "__main__":
    main()
