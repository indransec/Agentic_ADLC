"""Run detail and sign-off (SA 8.2; FR-008 to FR-011).

Every section is shown whether or not it has content. Agent and person text is plain text. The
decision form is built from the API's ``form``; the run version the person saw goes with every
action, and a stale answer reloads the page with a message.
"""

from collections.abc import Callable
from functools import partial
from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import error, field, table

STALE_NOTE = "stale_note"
MAX_EDIT_ROWS = 1000  # research R-11: larger tables are read-only, with upload offered
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FALLBACK_DOWNLOAD = "application/octet-stream"


def render(api: ApiClient) -> None:
    st.header("Run")
    run_id = st.text_input("Run", value=st.session_state.get("run_id", ""), key="run_input")
    if not run_id:
        st.caption("Open a run from the inbox or a use case.")
        return
    data, seen = load(api, run_id)
    header(data)
    artifacts(api, data, seen)
    sections(data)
    decision_form(api, data, seen)


def load(api: ApiClient, run_id: str) -> tuple[dict[str, Any], int]:
    """The run detail and the version the person saw (FR-011).

    The version the person saw is the one shown on the previous render: a click re-runs the page
    and fetches again, and acting on that fresh version would hide a concurrent change.
    """
    st.session_state["run_id"] = run_id
    if note := st.session_state.pop(STALE_NOTE, None):
        st.warning(note)
    data = api.get(f"/runs/{run_id}")
    seen_key = f"seen:{run_id}"
    seen = int(st.session_state.get(seen_key, data["run"]["version"]))
    st.session_state[seen_key] = data["run"]["version"]
    return data, seen


def header(data: dict[str, Any]) -> None:
    run = data["run"]
    field("Terminal", f"{run['terminal_id']} (spec {data['spec']['version']})")
    field(
        "State", run["state"] + (" - controls are being re-run" if run["controls_pending"] else "")
    )
    field("Version", run["version"])
    timer = data["timer"]
    field("Due", f"{timer['due_at']}{' (overdue)' if timer['overdue'] else ''}")


def act(call: Callable[[], Any], done: str) -> None:
    """Run one action; a stale answer reloads the page with a message (FR-011)."""
    try:
        call()
    except ApiError as exc:
        if exc.kind == "stale":
            st.session_state[STALE_NOTE] = (
                "This run changed since you opened it. It has been reloaded; check it and act "
                "again."
            )
            st.rerun()
        error(exc)
        return
    st.success(done)


def artifacts(api: ApiClient, data: dict[str, Any], seen: int) -> None:
    st.subheader("Artifacts")
    run_id = data["run"]["run_id"]
    editable = data["form"]["can_edit"]
    for artifact in data["artifacts"]:
        aid = artifact["id"]
        key = f"{run_id}:{aid}"
        st.caption(aid)
        rows = artifact["rows"]
        if not isinstance(rows, list):
            st.text("" if rows is None else str(rows))
        elif editable and len(rows) <= MAX_EDIT_ROWS:
            edited = st.data_editor(
                [{c: row.get(c) for c in artifact["columns"] or row} for row in rows],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key=f"edit:{key}",
            )
            if st.button(f"Save {aid}", key=f"save:{key}"):
                body = {"rows": edited, "expected_version": seen}
                act(partial(api.put, f"/runs/{run_id}/artifacts/{aid}", body), "Saved")
        else:
            table(rows)
            if editable:
                st.caption(f"More than {MAX_EDIT_ROWS} rows: upload a spreadsheet to change it.")
        for attachment in artifact["attachments"]:
            content = api.get(f"/runs/{run_id}/attachments/{attachment['content_hash']}")
            st.text(attachment["name"])  # a person's file name: plain text, never a label
            st.download_button(
                "Download",
                data=content,
                file_name=attachment["name"],
                mime=FALLBACK_DOWNLOAD,  # never rendered in the browser
                key=f"download:{key}:{attachment['content_hash']}",
            )
        if editable:
            uploads(api, run_id, aid, seen)
        if st.toggle("History", key=f"history:{key}"):
            table(api.get(f"/runs/{run_id}/artifacts/{aid}/history"))


def uploads(api: ApiClient, run_id: str, aid: str, seen: int) -> None:
    key = f"{run_id}:{aid}"
    base = f"/runs/{run_id}/artifacts/{aid}"
    sheet = st.file_uploader(f"Spreadsheet for {aid}", type=["xlsx"], key=f"sheet:{key}")
    if sheet is not None and st.button(f"Upload spreadsheet to {aid}", key=f"upload:{key}"):
        data = sheet.getvalue()
        act(
            lambda: api.upload(f"{base}/spreadsheet", sheet.name, data, XLSX, seen),
            "Spreadsheet uploaded",
        )
    file = st.file_uploader(f"Attach a file to {aid}", key=f"file:{key}")
    if file is not None and st.button(f"Attach to {aid}", key=f"attach:{key}"):
        data = file.getvalue()
        media = file.type or FALLBACK_DOWNLOAD
        act(lambda: api.upload(f"{base}/attachments", file.name, data, media, seen), "Attached")


def sections(data: dict[str, Any]) -> None:
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

    st.subheader("Evidence")
    st.caption("Checks")
    table(data["checks"])
    st.caption("Checklist results")
    table(data["checklist_results"] or [])
    st.caption("Artifact versions")
    table([{"artifact": a["id"], **(a["version"] or {})} for a in data["artifacts"]])
    st.caption("Ledger record")
    record = data["ledger_record"]
    st.text("(not yet recorded: the run is open)" if record is None else str(record))


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
        act(lambda: api.post(f"/runs/{key}/decisions", body), "Decision recorded")
