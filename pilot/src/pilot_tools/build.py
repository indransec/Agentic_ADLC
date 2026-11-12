"""``pilot-build``: validate a fill and build the package (FR-002, FR-003; research R-02).

The package is a deterministic ``.tar.gz`` of the template's agent code, reference data,
infrastructure definitions and ``template.yaml``, plus the fill: entries sorted, times and owners
zeroed, modes normalised, gzip header time zero. Its sha256 is the package hash.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from triage_agent.fill import FillError, load_fill, template_spec

TEMPLATE_PARTS = ("template.yaml", "agent", "reference", "infra")
SKIP = ("__pycache__", ".pyc", ".DS_Store")


class BuildError(Exception):
    pass


@dataclass(frozen=True)
class Built:
    package_hash: str
    archive: Path
    manifest: Path


def _files(template: Path, fill: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for part in TEMPLATE_PARTS:
        path = template / part
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for file in candidates:
            if not any(s in str(file) for s in SKIP):
                found.append((f"template/{file.relative_to(template).as_posix()}", file))
    for file in sorted(p for p in fill.rglob("*") if p.is_file()):
        if not any(s in str(file) for s in SKIP):
            found.append((f"fill/{file.relative_to(fill).as_posix()}", file))
    return sorted(found)


def _archive(files: list[tuple[str, Path]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, path in files:
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def build(template: Path, fill: Path, registry: Path) -> Built:
    try:
        fill_values = load_fill(template, fill)
    except FillError as exc:
        raise BuildError(f"fill part {exc.part} is invalid: {exc}") from None
    files = _files(template, fill)
    data = _archive(files)
    digest = hashlib.sha256(data).hexdigest()
    spec = template_spec(template)
    registry.mkdir(parents=True, exist_ok=True)
    archive, manifest = registry / f"{digest}.tar.gz", registry / f"{digest}.json"
    archive.write_bytes(data)
    manifest.write_text(
        json.dumps(
            {
                "package_hash": f"sha256:{digest}",
                "template_id": spec["id"],
                "template_version": spec["version"],
                "built_at": datetime.now(UTC).isoformat(),
                "files": {
                    name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                    for name, path in files
                },
                "fill_summary": {
                    "model_mode": fill_values.settings.model_mode,
                    "model_name": fill_values.settings.model_name,
                    "token_budget": fill_values.settings.token_budget,
                    "tools": sorted(fill_values.tools),
                },
            },
            indent=1,
        )
        + "\n"
    )
    return Built(f"sha256:{digest}", archive, manifest)


def digest_of(package_hash: str) -> str:
    prefix, _, digest = package_hash.partition(":")
    if prefix != "sha256" or len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
        raise BuildError(f"not a package hash: {package_hash!r}")
    return digest


def exists(registry: Path, package_hash: str) -> bool:
    try:
        return (registry / f"{digest_of(package_hash)}.tar.gz").is_file()
    except BuildError:
        return False


def extract(registry: Path, package_hash: str, destination: Path) -> Path:
    """Unpack a registered package into ``destination`` (checked against its hash)."""
    archive = registry / f"{digest_of(package_hash)}.tar.gz"
    if not archive.is_file():
        raise BuildError(f"unknown package {package_hash}")
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest_of(package_hash):
        raise BuildError(f"package {package_hash} does not match its hash")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(destination, filter="data")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(prog="pilot-build", description=__doc__)
    parser.add_argument("--fill", type=Path, required=True)
    parser.add_argument(
        "--template", type=Path, default=Path(os.environ.get("PILOT_TEMPLATE", "template"))
    )
    parser.add_argument(
        "--registry", type=Path, default=Path(os.environ.get("PILOT_REGISTRY", "/packages"))
    )
    args = parser.parse_args()
    try:
        built = build(args.template, args.fill, args.registry)
    except BuildError as exc:
        print(f"pilot-build: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(built.package_hash)
