"""Use cases and their journey (runs per terminal with status, time and cost)."""

import streamlit as st

from adlc.ui import format as fmt
from adlc.ui.client import ApiClient
from adlc.ui.render import (
    field,
    navigate,
    open_picker,
    page_header,
    status_badge,
    status_text,
    table,
)


def render(api: ApiClient) -> None:
    page_header("Use cases", "Every use case, its runs through the terminals, and its evidence.")
    if submitted := st.session_state.pop("submitted", None):
        st.session_state.pop("journey_usecase", None)  # show the new use case's journey
        st.success("Submitted", icon=":material/check_circle:")
        st.text(submitted)
    mine = st.toggle("Only mine", value=True, key="mine")
    found = api.get("/usecases", mine=str(mine).lower())
    ids = [u["usecase_id"] for u in found]
    table(
        [
            {
                "use case": u["usecase_id"],
                "name": u["name"],
                "submitted by": u["submitted_by"],
                "status": status_text(u["status"]),
                "open runs": u["open_runs"],
            }
            for u in found
        ],
        empty_text="No use cases yet." if not mine else "You have not submitted a use case yet.",
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
    st.subheader("Journey", anchor=False)
    with st.container(border=True):
        name, submitted, risk, cost = st.columns([3, 2, 2, 2])
        with name:
            field("Name", usecase["name"])
        with submitted:
            field("Submitted by", usecase["submitted_by"])
        with risk:
            st.caption("Risk tier")
            status_badge(usecase["risk_tier"])
        with cost:
            field("Total cost", fmt.money(data["cost"]["total"].get("cost_usd")))
        with st.expander("Description", expanded=False, icon=":material/description:"):
            st.text(usecase["intake_text"])  # the submitter's words: plain text
    costs = data["cost"]["terminals"]
    summary = {s["terminal_id"]: s for s in data["summary"]}
    table(
        [
            {
                "run": r["run_id"],
                "terminal": r["terminal_id"],
                "state": status_text(r["state"]),
                "status": status_text(r["final_status"]),
                "opened": r["opened_at"],
                "closed": r["closed_at"],
                "automatic": fmt.duration(
                    summary.get(r["terminal_id"], {}).get("automatic_seconds", 0)
                ),
                "waiting": fmt.duration(
                    summary.get(r["terminal_id"], {}).get("waiting_seconds", 0)
                ),
                "cost": fmt.money(costs.get(r["terminal_id"], {}).get("cost_usd")),
            }
            for r in data["runs"]
        ],
        key="journey_runs",
        empty_text="No runs yet: the first terminal opens shortly after submission.",
    )
    run_ids = [r["run_id"] for r in data["runs"]]
    if pick := open_picker(run_ids, select_key="journey_run", button_key="open_run", label="Run"):
        navigate("Run", run_id=pick)
    if st.button("Open the journey view", key="open_journey", icon=":material/timeline:"):  # 013
        navigate("Journey", journey_pick=usecase_id)
    st.subheader("Evidence", anchor=False)
    with st.container(border=True):
        st.caption("Check this use case's ledger records for breaks.")
        if st.button(
            "Verify the ledger for this use case", key="verify", icon=":material/verified:"
        ):
            report = api.post(f"/usecases/{usecase_id}/verify")
            if report["verified"]:
                st.success(
                    f"Verified: {report['records_checked']} records, no breaks",
                    icon=":material/verified:",
                )
            else:
                st.error(f"{len(report['breaks'])} break(s) found", icon=":material/error:")
                table(report["breaks"])
