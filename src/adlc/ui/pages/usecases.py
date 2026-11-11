"""Use cases and their journey (runs per terminal with status, time and cost)."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import field, navigate, table


def render(api: ApiClient) -> None:
    st.header("Use cases")
    mine = st.toggle("Only mine", value=True, key="mine")
    found = api.get("/usecases", mine=str(mine).lower())
    ids = [u["usecase_id"] for u in found]
    table(
        [
            {
                "use case": u["usecase_id"],
                "name": u["name"],
                "submitted by": u["submitted_by"],
                "status": u["status"],
                "open runs": u["open_runs"],
            }
            for u in found
        ]
    )
    if not ids:
        return
    chosen = st.session_state.get("usecase_id")
    index = ids.index(chosen) if chosen in ids else 0
    usecase_id = st.selectbox("Use case", ids, index=index, key="journey_usecase")
    st.session_state["usecase_id"] = usecase_id
    journey(api, usecase_id)


def journey(api: ApiClient, usecase_id: str) -> None:
    data = api.get(f"/usecases/{usecase_id}")
    usecase = data["usecase"]
    st.subheader("Journey")
    field("Name", usecase["name"])
    field("Submitted by", usecase["submitted_by"])
    field("Risk tier", usecase["risk_tier"])
    costs = data["cost"]["terminals"]
    summary = {s["terminal_id"]: s for s in data["summary"]}
    table(
        [
            {
                "run": r["run_id"],
                "terminal": r["terminal_id"],
                "state": r["state"],
                "status": r["final_status"],
                "opened": r["opened_at"],
                "closed": r["closed_at"],
                "automatic s": round(summary.get(r["terminal_id"], {}).get("automatic_seconds", 0)),
                "waiting s": round(summary.get(r["terminal_id"], {}).get("waiting_seconds", 0)),
                "cost USD": costs.get(r["terminal_id"], {}).get("cost_usd"),
            }
            for r in data["runs"]
        ],
        key="journey_runs",
    )
    run_ids = [r["run_id"] for r in data["runs"]]
    if run_ids:
        pick = st.selectbox("Open run", run_ids, key="journey_run")
        if st.button("Open", key="open_run"):
            navigate("Run", run_id=pick)
    field("Total cost (USD)", data["cost"]["total"].get("cost_usd"))
    st.subheader("Evidence")
    if st.button("Verify the ledger for this use case", key="verify"):
        report = api.post(f"/usecases/{usecase_id}/verify")
        if report["verified"]:
            st.success(f"Verified: {report['records_checked']} records, no breaks")
        else:
            st.error(f"{len(report['breaks'])} break(s) found")
            table(report["breaks"])
