"""T028: evidence sections and ledger verification in the web application (US5)."""

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import go, open_ui, sign_in


def test_evidence_and_verify(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T2")
    at = sign_in(open_ui(api), "business_owner")
    at.session_state["run_id"] = f"{usecase}/T1/run-1"
    at = go(at, "Run")
    assert not at.exception, at.exception
    assert "Evidence" in [s.value for s in at.subheader]
    assert [c.value for c in at.caption if c.value in ("Checks", "Ledger record")] == [
        "Checks",
        "Ledger record",
    ]
    at = go(at, "Use cases")
    at.button(key="verify").click()
    at = at.run()
    assert not at.exception, at.exception
    assert at.success and at.success[0].value.startswith("Verified:")
