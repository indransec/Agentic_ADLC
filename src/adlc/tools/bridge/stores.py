"""``ci``, ``artifact_store`` and ``prompt_registry`` (feature 010 US2, FR-011, FR-012).

CI reads the fill at a commit of the run's branch and asks ``pilot-lab`` to validate, build,
check reproducibility and smoke-test it; the hash is the pilot's own. The artifact store reads
manifests from the pilot's registry and keeps content-addressed build notes; the prompt registry
keeps instruction texts by sha256. Texts live on the bridge volume.
"""

import hashlib
import re
from pathlib import Path
from typing import Any

from adlc.tools.bridge.git_repo import GitRepos
from adlc.tools.bridge.pilot import Pilot
from adlc.tools.bridge.records import Records
from adlc.tools.mcp_app import Call, Handler, ToolFailure

SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_TEXT = 50_000


class TextStore:
    """Content-addressed texts in one folder: the name is the text's sha256."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def put(self, text: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{digest}.txt"
        if not path.exists():
            path.write_text(text)
        return f"sha256:{digest}"

    def get(self, sha: str) -> str:
        if not SHA.match(sha):
            raise ToolFailure("invalid arguments: sha256:<64 hex>")
        path = self.folder / f"{sha.removeprefix('sha256:')}.txt"
        if not path.exists():
            raise ToolFailure(f"not found: {sha}")
        return path.read_text()


def handlers(pilot: Pilot, repos: GitRepos, data: Path, records: Records) -> dict[str, Handler]:
    notes, prompts = TextStore(data / "artifacts"), TextStore(data / "prompts")

    def ci_run(call: Call, args: dict[str, Any]) -> Any:
        commit, files = repos.files_at(
            call.claims.usecase_id, call.bound("branch"), args.get("commit")
        )
        result = pilot.request(
            "POST", pilot.urls.lab, "/build", json={"files": files}, timeout_s=85
        )
        checks = list(result.get("checks") or [])
        # 011 (contracts/ci-report.md): the whole report, which T3's controls read as evidence
        report = ("tests", "scans", "sbom", "observability")
        answer: dict[str, Any] = {"commit": commit, "checks": checks}
        answer.update({k: result[k] for k in report if k in result})
        if result.get("package_hash") and all(c.get("passed") for c in checks):
            answer["package_hash"] = result["package_hash"]
        return answer

    def artifact_store_read(call: Call, args: dict[str, Any]) -> Any:
        package = str(args.get("package_hash") or "")
        if not SHA.match(package):
            raise ToolFailure("invalid arguments: package_hash must be sha256:<64 hex>")
        return pilot.request("GET", pilot.urls.lab, f"/packages/{package}")

    def artifact_store_write(call: Call, args: dict[str, Any]) -> Any:
        text = str(args.get("text") or "")
        if not text or len(text) > MAX_TEXT:
            raise ToolFailure(f"invalid arguments: text of 1 to {MAX_TEXT} characters")
        sha = notes.put(text)
        records.add(
            "artifacts",
            usecase_id=call.claims.usecase_id,
            run_id=call.claims.run_id,
            name=str(args.get("name") or "")[:200],
            sha256=sha,
        )
        return {"sha256": sha}

    def prompt_registry_write(call: Call, args: dict[str, Any]) -> Any:
        text = str(args.get("text") or "")
        if not text or len(text) > MAX_TEXT:
            raise ToolFailure(f"invalid arguments: text of 1 to {MAX_TEXT} characters")
        sha = prompts.put(text)
        records.add(
            "prompts", usecase_id=call.claims.usecase_id, run_id=call.claims.run_id, sha256=sha
        )
        return {"sha256": sha}

    def prompt_registry_read(call: Call, args: dict[str, Any]) -> Any:
        sha = str(args.get("sha256") or "")
        return {"sha256": sha, "text": prompts.get(sha)}

    return {
        "ci_run": ci_run,
        "artifact_store_read": artifact_store_read,
        "artifact_store_write": artifact_store_write,
        "prompt_registry_write": prompt_registry_write,
        "prompt_registry_read": prompt_registry_read,
    }
