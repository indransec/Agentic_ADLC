"""Run detail and sign-off (SA 8.2; FR-008 to FR-011).

Every section is shown whether or not it has content. What a sign-off needs in front of the
person (artifacts, reviewer recommendation, control results) sits beside the decision form; the
other sections are tabs below. Agent and person text is plain text. The decision form is built from
the API's ``form``; the run version the person saw goes with every action, and a stale answer
reloads the page with a message. The run is in the address (``?run=``), so a reload keeps it.
"""

import json
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

import streamlit as st

from adlc.ui import format as fmt
from adlc.ui import mode
from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import (
    STATUS,
    empty,
    error,
    field,
    page_header,
    status_badge,
    table,
)

STALE_NOTE = "stale_note"
MAX_EDIT_ROWS = 1000  # research R-11: larger tables are read-only, with upload offered
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FALLBACK_DOWNLOAD = "application/octet-stream"
CRUMBS = ("Delivery",)


def render(api: ApiClient) -> None:
    run_id = st.session_state.get("run_id") or st.query_params.get("run")
    if not run_id:
        page_header("Run", "A terminal run: its artifacts, the checks on them and the decision.")
        empty("Open a run from your inbox or a use case.")
        return
    data, seen = load(api, run_id)
    st.query_params["run"] = run_id  # a reload, or the address shared, opens this run
    page_header("Run", crumbs=CRUMBS)
    header(data)
    left, right = st.columns([3, 2], gap="large")
    with left:
        artifacts(api, data, seen)
    with right:
        review(data)
        if mode.is_console(api):
            board_decision(api, data)  # 019: people decide on the board
        else:
            decision_form(api, data, seen)
    details(api, data)


def load(api: ApiClient, run_id: str) -> tuple[dict[str, Any], int]:
    """The run detail and the version the person saw (FR-011).

    The version the person saw is the one shown on the previous render: a click re-runs the page
    and fetches again, and acting on that fresh version would hide a concurrent change.
    """
    st.session_state["run_id"] = run_id
    if note := st.session_state.pop(STALE_NOTE, None):
        st.warning(note, icon=":material/sync_problem:")
    data = api.get(f"/runs/{run_id}")
    seen_key = f"seen:{run_id}"
    seen = int(st.session_state.get(seen_key, data["run"]["version"]))
    st.session_state[seen_key] = data["run"]["version"]
    return data, seen


def header(data: dict[str, Any]) -> None:
    """The run at a glance: which run, its state, when it is due and what it has cost."""
    run = data["run"]
    timer = data["timer"]
    with st.container(border=True):
        ident, terminal, state, due, cost = st.columns([3, 2, 2, 2, 1.5])
        with ident:
            field("Run", run["run_id"])
            st.caption(f"Version {run['version']}")
        with terminal:
            field("Terminal", f"{run['terminal_id']} · spec {data['spec']['version']}")
        with state:
            st.caption("State")
            status_badge(run["state"])
            if run.get("final_status"):
                status_badge(run["final_status"])
            if run["controls_pending"]:
                st.caption(":material/sync: Controls are being re-run")
        with due:
            st.caption("Due")
            st.text(fmt.when(timer["due_at"]))
            if timer["overdue"]:
                st.badge("Overdue", color="red", icon=":material/alarm:")
        with cost:
            field("Model cost", fmt.money(data["cost"].get("cost_usd")))
    if run["state"] == "blocked":
        st.warning(
            "Blocked by an unmet prerequisite (see Prerequisites). Supply the evidence, or "
            "terminate the run below.",
            icon=":material/block:",
        )


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
    st.success(done, icon=":material/check_circle:")


# ------------------------------------------------------------------------------ artifacts


def artifacts(api: ApiClient, data: dict[str, Any], seen: int) -> None:
    st.subheader("Artifacts", anchor=False)
    run_id = data["run"]["run_id"]
    editable = data["form"]["can_edit"]
    if not data["artifacts"]:
        empty("This terminal produces no artifacts.")
    for artifact in data["artifacts"]:
        with st.container(border=True):
            artifact_card(api, run_id, artifact, editable, seen)


def artifact_card(
    api: ApiClient, run_id: str, artifact: dict[str, Any], editable: bool, seen: int
) -> None:
    aid = artifact["id"]
    key = f"{run_id}:{aid}"
    version = artifact.get("version") or {}
    name, meta = st.columns([3, 2], vertical_alignment="center")
    name.markdown(f"**{aid}**")  # the spec's artifact id
    meta.caption(f"Version {version['version']}" if version.get("version") else "Not built yet")
    rows = artifact["rows"]
    if not isinstance(rows, list):
        st.text("" if rows is None else str(rows))
    elif editable and len(rows) <= MAX_EDIT_ROWS:
        edited = st.data_editor(
            [{c: row.get(c) for c in artifact["columns"] or row} for row in rows],
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=f"edit:{key}",
        )
        if st.button(f"Save {aid}", key=f"save:{key}", icon=":material/save:"):
            body = {"rows": edited, "expected_version": seen}
            act(partial(api.put, f"/runs/{run_id}/artifacts/{aid}", body), "Saved")
    else:
        table(rows, labels=False)
        if editable:
            st.caption(f"More than {MAX_EDIT_ROWS} rows: upload a spreadsheet to change it.")
    for attachment in artifact["attachments"]:
        content = api.get(f"/runs/{run_id}/attachments/{attachment['content_hash']}")
        name_column, button_column = st.columns([4, 1], vertical_alignment="center")
        with name_column:
            st.text(attachment["name"])  # a person's file name: plain text, never a label
        button_column.download_button(
            "Download",
            data=content,
            file_name=attachment["name"],
            mime=FALLBACK_DOWNLOAD,  # never rendered in the browser
            key=f"download:{key}:{attachment['content_hash']}",
            icon=":material/download:",
            width="stretch",
        )
    if editable:
        with st.expander("Upload a spreadsheet or attach a file", icon=":material/upload_file:"):
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


# ------------------------------------------------------------------ review and controls


def review(data: dict[str, Any]) -> None:
    """What the sign-off rests on besides the artifacts (SA 8.2)."""
    recommendation_section(data["recommendation"])
    controls_section(data["control_results"])


def recommendation_section(recommendation: dict[str, Any] | None) -> None:
    st.subheader("Reviewer recommendation", anchor=False)
    if recommendation is None:
        empty("No recommendation yet.")
        return
    with st.container(border=True):
        status = recommendation.get("status")
        if str(status) in STATUS:
            status_badge(status, text=f"Recommends {status}")
        else:
            field("Recommended", status)
        field("Reason", recommendation.get("reason"))
        if recommendation.get("root_cause"):
            field("Root cause", recommendation.get("root_cause"))
        if recommendation.get("items"):
            st.caption("Checklist")
            table(recommendation.get("items", []), key="run_recommendation_items")
        findings = recommendation.get("findings", [])
        if findings:
            st.caption("Findings")
            for finding in findings:
                st.text(str(finding))


def controls_section(results: list[Any]) -> None:
    st.subheader("Control results", anchor=False)
    checked = [c for c in results if isinstance(c, Mapping)]
    if checked:
        passed = sum(1 for c in checked if c.get("passed"))
        blocking = sum(1 for c in checked if c.get("blocking") and not c.get("passed"))
        badges = [
            f":{'green' if passed == len(checked) else 'orange'}-badge[{passed} of "
            f"{len(checked)} passed]"
        ]
        if blocking:
            badges.append(f":red-badge[:material/block: {blocking} blocking failed]")
        st.markdown(" ".join(badges))  # counts only: platform text
    table(results, key="run_controls", empty_text="No controls have run yet.")


# ------------------------------------------------------------------------------ decision


def board_decision(api: ApiClient, data: dict[str, Any]) -> None:
    """019 (research R-06): the decision is made on the board; link to the run's work item."""
    st.subheader("Decision", anchor=False)
    st.info("The decision on this run is made on the board.", icon=":material/view_kanban:")
    url = mode.item_url(api, "run", str(data["run"]["run_id"]))
    if url:
        st.link_button("Decide on the board", url, type="primary", icon=":material/open_in_new:")
    else:
        empty("This run is not on the board yet; the board sync will add it shortly.")


def decision_form(api: ApiClient, data: dict[str, Any], seen: int) -> None:
    form = data["form"]
    run = data["run"]
    st.subheader("Decision", anchor=False)
    if form["controls_pending"]:
        st.info(
            "Controls are being re-run after an edit; deciding is possible once they finish.",
            icon=":material/sync:",
        )
    if form["waiver_pending"]:
        st.info("A waiver is pending its approver's decision.", icon=":material/hourglass_top:")
    if not (form["can_decide"] or form["can_terminate"]):
        empty("You have no decision to make on this run.")
        return
    outcomes = form["outcomes"] if form["can_decide"] else ["terminate"]
    key = run["run_id"]
    with st.container(border=True):
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

        if st.button(
            "Submit decision",
            key=f"submit:{key}",
            type="primary",
            icon=":material/gavel:",
            width="stretch",
        ):
            act(lambda: api.post(f"/runs/{key}/decisions", body), "Decision recorded")


# ------------------------------------------------------------------------------ the rest


def counted(name: str, rows: Any) -> str:
    return f"{name} ({len(rows)})" if isinstance(rows, list) and rows else name


def details(api: ApiClient, data: dict[str, Any]) -> None:
    """The other SA 8.2 sections, one tab each; every tab is there whether or not it has content."""
    citations = [
        {"artifact": a["id"], **c} for a in data["artifacts"] for c in a.get("citations") or []
    ]
    tabs = st.tabs(
        [
            counted("Prerequisites", data["prerequisites"]),
            counted("Citations", citations),
            counted("Prior rework", data["prior_rework"]),
            counted("Clarifications", data["clarifications"]),
            counted("Approvals", data["approvals"]),
            "Waiver",
            "Activity",
            "Timeline",
            "Evidence",
        ]
    )
    with tabs[0]:
        table(data["prerequisites"], key="run_prerequisites")
    with tabs[1]:
        table(citations, key="run_citations")
    with tabs[2]:
        table(data["prior_rework"], key="run_prior_rework")
    with tabs[3]:
        table(data["clarifications"], key="run_clarifications")
    with tabs[4]:
        table(data["approvals"], key="run_approvals", empty_text="No approvals yet.")
    with tabs[5]:
        waiver = data["waiver"]
        if waiver is None:
            empty("No waiver on this run.")
        else:
            table(
                [{"field": fmt.label(k), "value": v} for k, v in waiver.items()],
                key="run_waiver",
            )
    with tabs[6]:
        table(data["timeline"], key="run_activity")
    with tabs[7]:
        timeline(api, data["run"]["run_id"])
    with tabs[8]:
        evidence(data)


def evidence(data: dict[str, Any]) -> None:
    st.caption("Checks")
    table(data["checks"], key="run_checks")
    st.caption("Checklist results")
    table(data["checklist_results"] or [], key="run_checklist")
    st.caption("Artifact versions")
    table(
        [{"artifact": a["id"], **(a["version"] or {})} for a in data["artifacts"]],
        key="run_versions",
    )
    st.caption("Ledger record")
    record = data["ledger_record"]
    if record is None:
        empty("Not yet recorded: the run is open.")
    else:
        st.code(json.dumps(record, indent=2, default=str, ensure_ascii=False), language="json")


def timeline(api: ApiClient, run_id: str) -> None:
    """013 US4: the step timeline with durations, and each attempt's model and tool calls."""
    found = api.get(f"/dashboard/runs/{run_id}/timeline")
    table(found["activity"], key="run_timeline_activity")
    for attempt in found["attempts"]:
        with st.container(border=True):
            st.caption(
                f"{attempt['kind'].capitalize()} attempt {attempt['attempt']} · "
                f"{attempt['agent_id']} ({attempt['implementation']}) · "
                f"{attempt['tokens_in'] or 0:,} in + {attempt['tokens_out'] or 0:,} out tokens · "
                f"{fmt.money(attempt['cost_usd'])}"
            )
            ident = f"{attempt['kind']}_{attempt['attempt']}"
            table(attempt["model_calls"], key=f"run_timeline_models_{ident}")
            table(attempt["tool_calls"], key=f"run_timeline_tools_{ident}")


def sections(api: ApiClient, data: dict[str, Any]) -> None:
    """Everything but the artifacts and the decision (the escalation page shows these)."""
    review(data)
    details(api, data)
