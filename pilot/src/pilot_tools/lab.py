"""``pilot-lab`` (feature 010, contracts/pilot-additions.md): builds and datasets for the platform's
CI, artifact store and evaluation harness, on the pilot network. The platform's bridge calls it;
the platform never imports pilot code.

- ``GET /layout``: the fill files T3 may write (the template's fill points).
- ``POST /build``: validate a fill, build the package into the registry, rebuild to check
  reproducibility, and smoke-test the package (start it in-process and triage a few incidents).
- ``GET /packages/{hash}``: a package's manifest.
- ``GET /datasets`` and ``GET /datasets/{id}``: approved datasets, generated with their seed.
"""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from pilot_tools.build import BuildError, build, digest_of, exists, extract
from pilot_tools.incidents import generate
from triage_agent.app import create_app as package_app
from triage_agent.fill import FillError, load_fill, template_spec

SMOKE_SEED, SMOKE_SIZE = 1, 5
MAX_FILE = 200_000


class Build(BaseModel):
    files: dict[str, str] = Field(max_length=20)


def layout(template: Path) -> list[str]:
    points = template_spec(template).get("fill_points") or {}
    return sorted(str(p["file"]) for p in points.values())


def _canonical_sha(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def _smoke(registry: Path, package_hash: str, template: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as work:
        root = extract(registry, package_hash, Path(work) / "package")
        client = TestClient(package_app(root, package_hash))
        for incident in generate(SMOKE_SEED, SMOKE_SIZE, template=template):
            request = {k: v for k, v in incident.items() if k not in ("expected", "planted_pii")}
            answer = client.post("/triage", json=request)
            if answer.status_code != 200 or answer.json().get("package_hash") != package_hash:
                return _check("smoke", False, f"{incident['incident_id']}: {answer.status_code}")
            if not answer.json().get("team"):
                return _check("smoke", False, f"{incident['incident_id']}: no team")
    return _check("smoke", True, f"{SMOKE_SIZE} incidents answered")


def create_lab(template: Path, registry: Path, datasets_file: Path) -> FastAPI:
    app = FastAPI(title="pilot-lab")
    declared = YAML(typ="safe").load(datasets_file.read_text())["datasets"]
    by_id = {str(d["id"]): d for d in declared}
    cache: dict[str, dict[str, Any]] = {}

    def dataset(dataset_id: str) -> dict[str, Any]:
        if dataset_id not in by_id:
            raise HTTPException(404, f"unknown dataset {dataset_id}")
        if dataset_id not in cache:
            d = by_id[dataset_id]
            rows = generate(int(d["seed"]), int(d["size"]), float(d["pii_share"]), template)
            meta = {
                "id": dataset_id,
                "version": str(d["version"]),
                "seed": int(d["seed"]),
                "size": int(d["size"]),
                "pii_share": float(d["pii_share"]),
                "sha256": _canonical_sha(rows),
                "scored_fields": list(d["scored_fields"]),
                "slices": list(d.get("slices") or []),
            }
            cache[dataset_id] = {"dataset": meta, "rows": rows}
        return cache[dataset_id]

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/layout")
    def get_layout() -> dict[str, Any]:
        spec = template_spec(template)
        return {
            "files": layout(template),
            "template_id": spec["id"],
            "template_version": spec["version"],
        }

    @app.post("/build")
    def post_build(body: Build) -> dict[str, Any]:
        allowed = set(layout(template))
        unknown = sorted(set(body.files) - allowed)
        if unknown or any(len(text) > MAX_FILE for text in body.files.values()):
            raise HTTPException(422, f"files outside the fill layout or too large: {unknown}")
        with tempfile.TemporaryDirectory() as work:
            fill = Path(work) / "fill"
            fill.mkdir()
            for name, text in body.files.items():
                (fill / name).write_text(text)
            try:
                load_fill(template, fill)
            except FillError as exc:
                return {"checks": [_check("validate", False, f"{exc.part}: {exc}")]}
            checks = [_check("validate", True)]
            try:
                built = build(template, fill, registry)
                again = build(template, fill, Path(work) / "again")
            except BuildError as exc:
                return {"checks": [*checks, _check("build", False, str(exc))]}
            checks.append(_check("build", True, built.package_hash))
            same = again.package_hash == built.package_hash
            checks.append(_check("reproducible", same, "" if same else again.package_hash))
            checks.append(_smoke(registry, built.package_hash, template))
            return {"checks": checks, "package_hash": built.package_hash}

    @app.get("/packages/{package_hash}")
    def manifest(package_hash: str) -> dict[str, Any]:
        if not exists(registry, package_hash):
            raise HTTPException(404, f"unknown package {package_hash}")
        data: dict[str, Any] = json.loads(
            (registry / f"{digest_of(package_hash)}.json").read_text()
        )
        return data

    @app.get("/datasets")
    def list_datasets() -> list[dict[str, Any]]:
        return [dataset(d)["dataset"] for d in by_id]

    @app.get("/datasets/{dataset_id}")
    def get_dataset(dataset_id: str) -> dict[str, Any]:
        return dataset(dataset_id)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(prog="pilot-lab", description="Pilot builds and datasets")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PILOT_LAB_PORT", "8300")))
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    app = create_lab(
        Path(os.environ.get("PILOT_TEMPLATE", project / "template")),
        Path(os.environ.get("PILOT_REGISTRY", "/packages")),
        Path(os.environ.get("PILOT_DATASETS", project / "datasets.yaml")),
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_config=None)  # noqa: S104


if __name__ == "__main__":
    main()
