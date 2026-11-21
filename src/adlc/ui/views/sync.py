"""Sync status (feature 019, US2; research R-07): the board sync's health for its operator.

016's ``/board/health`` as metrics, refusals by reason, the use cases whose board deliveries were
dead-lettered (each with re-queue), the last reconciliation's differences and "Reconcile now"
behind a confirmation. The API allows the CoE role only; the sidebar offers the page only to the
people the API says operate the sync. Every value from the platform's tables is plain text.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui import format as fmt
from adlc.ui import mode
from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import empty, page_header, table
from adlc.ui.views.run import act


def _age(seconds: Any) -> str:
    return "—" if seconds is None else fmt.duration(float(seconds))


def render(api: ApiClient) -> None:
    page_header(
        "Sync status",
        "The board sync between the platform and the board: how current it is, what it refused, "
        "and reconciliation.",
    )
    if not mode.can_operate(api):
        st.info("The board sync is operated by the CoE role.", icon=":material/lock:")
        return
    refresh = UiSettings().ui_dashboard_refresh.total_seconds()

    @st.fragment(run_every=refresh)
    def status() -> None:
        try:
            health = api.get("/board/health")
        except ApiError as exc:
            if exc.signed_out:
                raise
            st.warning("The sync status could not be read; it will be tried again.")
            return
        show(api, health)

    status()


def show(api: ApiClient, health: dict[str, Any]) -> None:
    if not health.get("enabled"):
        st.info(
            "The board sync is off (ADLC_BOARD_ENABLED is not true): people decide in the inbox.",
            icon=":material/sync_disabled:",
        )
        return
    if not health.get("mapping_ok", True):
        st.error("The tracker mapping does not fit the board: the sync is stopped until fixed.")
    first = st.columns(3)
    first[0].metric("Last poll", str(health.get("last_poll_outcome") or "none yet"))
    first[1].metric("Inbound watermark age", _age(health.get("watermark_age_s")))
    first[2].metric("Reverted board changes", str(health.get("reverted_count", 0)))
    second = st.columns(3)
    second[0].metric("Outbound pending", str(health.get("outbound_pending", 0)))
    second[1].metric("Oldest pending", _age(health.get("outbound_oldest_age_s")))
    second[2].metric("Dead-lettered use cases", str(len(health.get("dead_lettered") or [])))
    st.caption(f"Last poll at {health.get('last_poll_at') or '—'} (UTC)")

    st.subheader("Refused board changes", anchor=False)
    refused = health.get("refused_by_reason") or {}
    table(
        [{"reason": k, "count": v} for k, v in sorted(refused.items())],
        key="sync_refused",
        empty_text="No board change has been refused.",
    )

    st.subheader("Board deliveries dead-lettered", anchor=False)
    st.caption(
        "Use cases whose writes to the board failed after their retries. Re-queuing here retries "
        "the board delivery; platform events are on the Dead letters page."
    )
    dead = [str(u) for u in health.get("dead_lettered") or []]
    if not dead:
        empty("Every use case is delivered to the board.")
    for usecase in dead:
        left, right = st.columns([3, 1])
        left.text(usecase)
        if right.button("Re-queue", key=f"sync_requeue:{usecase}", icon=":material/replay:"):
            requeue(api, usecase)

    st.subheader("Reconciliation", anchor=False)
    last = health.get("last_reconciliation")
    if last:
        st.caption(f"Last: number {last['id']} at {last.get('at') or '—'} (UTC)")
        differences(api.get(f"/board/reconciliations/{last['id']}"), key="sync_last")
    else:
        empty("No reconciliation has run yet.")
    with st.container(border=True):
        sure = st.checkbox(
            "Compare every board item with the platform and correct the board",
            key="sync_reconcile_sure",
        )
        if st.button(
            "Reconcile now",
            key="sync_reconcile",
            type="primary",
            disabled=not sure,
            icon=":material/sync:",
        ):
            try:
                report = api.post("/board/reconciliations")
            except ApiError as exc:
                if exc.signed_out:
                    raise
                st.error(f"The reconciliation was refused: {exc.kind.replace('_', ' ')}")
            else:
                st.success("Reconciliation finished", icon=":material/check_circle:")
                differences(report, key="sync_new")


def requeue(api: ApiClient, usecase: str) -> None:
    act(lambda: api.post(f"/board/requeue/{usecase}"), "Re-queued")


def differences(report: dict[str, Any] | None, *, key: str) -> None:
    if not report:
        return
    found = report.get("differences") or []
    st.text(
        f"Outcome {report.get('outcome')}: {report.get('items_checked', 0)} items checked, "
        f"{report.get('created_items', 0)} created, {len(found)} differences"
    )
    if report.get("error"):
        st.text(f"Error: {report['error']}")
    table(
        [
            {
                "item": d.get("object_id"),
                "work item": d.get("work_item_id"),
                "field": d.get("field"),
                "action": d.get("action"),
            }
            for d in found[:500]
        ],
        key=key,
        empty_text="No differences: the board matched the platform.",
    )
    if len(found) > 500:
        st.caption(f"Showing 500 of {len(found)} differences.")
