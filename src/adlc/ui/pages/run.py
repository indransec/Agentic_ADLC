"""Run detail and sign-off (SA 8.2; FR-008 to FR-011).

Every section is shown whether or not it has content. Agent and person text is plain text. The
decision form is built from the API's ``form``; the run version the person saw goes with every
action, and a stale answer reloads the page with a message.
"""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import error, field, table

STALE_NOTE = "stale_note"


def render(api: ApiClient) -> None:
    st.header("Run")
    run_id = st.text_input("Run", value=st.session_state.get("run_id", ""), key="run_input")
    if not run_id:
        st.caption("Open a run from the inbox or a use case.")
        return
    st.session_state["run_id"] = run_id
    if note := st.session_state.pop(STALE_NOTE, None):
        st.warning(note)
    data = api.get(f"/runs/{run_id}")
    # The version the person saw is the one shown on the previous render: a click re-runs the
    # page and fetches again, and acting on that fresh version would hide a concurrent change.
    seen_key = f"seen:{run_id}"
    seen = int(st.session_state.get(seen_key, data["run"]["version"]))
    st.session_state[seen_key] = data["run"]["version"]
    header(data)
    sections(data)
    decision_form(api, data, seen)


def header(data: dict[str, Any]) -> None:
    run = data["run"]
    field("Terminal", f"{run['terminal_id']} (spec {data['spec']['version']})")
    field(
        "State", run["state"] + (" - controls are being re-run" if run["controls_pending"] else "")
    )
    field("Version", run["version"])
    timer = data["timer"]
    field("Due", f"{timer['due_at']}{' (overdue)' if timer['overdue'] else ''}")


def sections(data: dict[str, Any]) -> None:
    st.subheader("Artifacts")
    for artifact in data["artifacts"]:
        st.caption(artifact["id"])
        rows = artifact["rows"]
        if isinstance(rows, list):
            table(rows)
        else:
            st.text("" if rows is None else str(rows))
        if artifact["attachments"]:
            table(artifact["attachments"])

    st.subheader("Control results")
    table(data["control_results"])

    st.subheader("Reviewer recommendation")
    recommendation = data["recommendation"]
    if recommendation is None:
        st.caption("(none yet)")
    else:
        field("Recommended", recommendation.get("status"))
        field("Reason", recommendation.get("reason"))
        field("Root cause", recommendation.get("root_cause"))
        table(recommendation.get("items", []))
        st.caption("Findings")
        for finding in recommendation.get("findings", []):
            st.text(str(finding))

    st.subheader("Prior rework comments")
    table(data["prior_rework"])

    st.subheader("Clarifications")
    table(data["clarifications"])

    st.subheader("Approvals so far")
    table(data["approvals"])

    st.subheader("Waiver")
    st.text("(none)" if data["waiver"] is None else str(data["waiver"]))

    st.subheader("Cost")
    field("Model cost (USD)", data["cost"].get("cost_usd"))

    st.subheader("Activity")
    table(data["timeline"])


def decision_form(api: ApiClient, data: dict[str, Any], seen: int) -> None:
    form = data["form"]
    run = data["run"]
    st.subheader("Decision")
    if form["controls_pending"]:
        st.info("Controls are being re-run after an edit; deciding is possible once they finish.")
    if form["waiver_pending"]:
        st.info("A waiver is pending its approver's decision.")
    if not (form["can_decide"] or form["can_terminate"]):
        st.caption("You have no decision to make on this run.")
        return
    outcomes = form["outcomes"] if form["can_decide"] else ["terminate"]
    key = run["run_id"]
    decision = st.radio("Outcome", outcomes, key=f"decision:{key}", horizontal=True)
    body: dict[str, Any] = {"decision": decision, "expected_version": seen, "fields": {}}

    if decision in ("rework", "terminate"):
        body["comment"] = st.text_area("Comment", key=f"comment:{key}") or None
    if decision == "rework":
        cause = st.selectbox("Root cause", form["root_causes"], key=f"cause:{key}")
        body["root_cause"] = cause
        if cause in form["target_terminal_for"]:
            body["target_terminal"] = st.selectbox(
                "Owning terminal", form["target_terminals"], key=f"target:{key}"
            )
    for name in form["requires"].get(decision, []):
        body["fields"][name] = st.text_input(name.replace("_", " "), key=f"{name}:{key}")
    if decision == "pass":
        for name in form["typed_fields"]:
            body["fields"][name] = st.text_input(name.replace("_", " "), key=f"{name}:{key}")
        if form["alternatives"]:
            alternative = st.selectbox(
                "Alternative route", ["", *form["alternatives"]], key=f"alt:{key}"
            )
            if alternative:
                body["fields"]["alternative"] = alternative
    recommended = form["reason_required_unless"]
    if recommended and decision not in (recommended, "terminate"):
        st.caption(f"The reviewer recommended {recommended}; give your reason.")
        body["reason"] = st.text_area("Reason", key=f"reason:{key}") or None

    if st.button("Submit decision", key=f"submit:{key}"):
        try:
            api.post(f"/runs/{key}/decisions", body)
        except ApiError as exc:
            if exc.kind == "stale":
                st.session_state[STALE_NOTE] = (
                    "This run changed since you opened it. It has been reloaded; check it and "
                    "decide again."
                )
                st.rerun()
            error(exc)
            return
        st.success("Decision recorded")
