"""T020: the T0 intake agent drafts from the intake, grounded in knowledge, with citations, and
asks the business owner instead of guessing (US1; FR-004, FR-011, FR-015 to FR-017)."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.grounded import KNOWLEDGE, grounded
from tests.support.orchestration import SYNTHETIC, person
from tests.support.pg import PlatformDatabase

T0 = "t0-intake-agent"
DRAFT = load_synthetic_artifacts(SYNTHETIC)["T0"]  # rows in T0's declared columns
POLICY = "policies/data-classification-policy.md"


def tool(name: str, **arguments: Any) -> str:
    return json.dumps({"tool": {"name": name, "arguments": arguments}})


def artifacts(citations: list[dict[str, Any]] | None = None) -> str:
    answer: dict[str, Any] = {"artifacts": DRAFT}
    if citations is not None:
        answer["citations"] = citations
    return json.dumps(answer)


CITE = {
    "artifact": "data_access",
    "row": 0,
    "source": "sharepoint",
    "document": POLICY,
    "section": "Claims data",
}
GROUNDED = [
    tool("sharepoint_search", query="claims data owner classification"),
    tool("sharepoint_read", document=POLICY, section="Claims data"),
    artifacts([CITE]),
]


def test_t0_builds_grounded_artifacts_with_citations(orch_template: PlatformDatabase) -> None:
    with grounded(orch_template, {T0: GROUNDED}) as g:
        h = g.h
        usecase = h.submit()
        run = h.active(usecase, "T0")
        assert run.state == "awaiting_sign_off", run.state
        attempt = h.sql(
            "SELECT implementation, prompt_hash, playbook_hashes, outcome FROM run.agent_attempt "
            "WHERE run_id = :r AND kind = 'build'",
            r=run.run_id,
        )[-1]
        assert attempt[0] == "model" and attempt[1].startswith("sha256:")
        assert set(attempt[2]) == {"PB-T0-01", "PB-T0-02", "PB-T0-03"} and attempt[3] == "artifacts"
        retrieved = h.sql(
            "SELECT source, operation, document, section, content_hash, synthetic "
            "FROM run.knowledge_retrieval WHERE run_id = :r ORDER BY knowledge_retrieval_id",
            r=run.run_id,
        )
        assert retrieved and all(r[0] == "sharepoint" and r[5] for r in retrieved)
        read = next(r for r in retrieved if r[1] == "read")
        (cited,) = h.sql(
            "SELECT artifact_id, version, row_index, document, section, content_hash "
            "FROM run.artifact_citation WHERE run_id = :r",
            r=run.run_id,
        )
        assert tuple(cited) == ("data_access", 1, 0, POLICY, "Claims data", read[4])
        assert all(set(rows[0]) == set(DRAFT[aid][0]) for aid, rows in run.artifacts.items())


def test_a_missing_fact_asks_the_business_owner(orch_template: PlatformDatabase) -> None:
    ask = json.dumps(
        {
            "clarification": {
                "questions": ["Who owns the claims history data?"],
                "addressed_role": "business_owner",
                "looked_in": ["sharepoint:/policies", "confluence:/business-capabilities"],
            }
        }
    )
    with grounded(orch_template, {T0: [ask, artifacts()]}) as g:
        h = g.h
        usecase = h.submit()
        run = h.active(usecase, "T0")
        assert run.state == "awaiting_clarification"
        (round_,) = h.sql(
            "SELECT clarification_id, addressed_role, looked_in "
            "FROM run.clarification_round WHERE run_id = :r",
            r=run.run_id,
        )
        assert round_[1] == "business_owner" and "sharepoint:/policies" in round_[2]
        h.service.answer_clarification(person("business_owner"), round_[0], ["claims operations"])
        h.drain()
        again = h.run(run.run_id)
        assert again.state == "awaiting_sign_off" and again.run_id == run.run_id


def test_citation_keeps_the_hash_of_what_was_read(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    folder = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE, folder)
    with grounded(orch_template, {T0: GROUNDED}, folder=folder) as g:
        usecase = g.h.submit()
        run_id = g.h.active(usecase, "T0").run_id
        text = (folder / "sharepoint" / POLICY).read_text()
        (folder / "sharepoint" / POLICY).write_text(text.replace("masked copies", "full copies"))
        (cited,) = g.h.sql(
            "SELECT content_hash FROM run.artifact_citation WHERE run_id = :r", r=run_id
        )
        section = text.split("## Claims data", 1)[1].split("\n## ", 1)[0]
        expected = (
            "sha256:" + hashlib.sha256(("## Claims data" + section).strip().encode()).hexdigest()
        )
        assert cited[0] == expected  # the text that was read, not the changed file
