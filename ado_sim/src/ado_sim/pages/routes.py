"""Page routes (017 contracts/pages.md): sign-in, the board, its columns fragment, the create
form and the read-only item page. Every change goes through the simulator's own store as the
signed-in user, so validation and history are the API's (SC-003).
"""

from __future__ import annotations

import html
import secrets
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ado_sim.comments import list_comments
from ado_sim.db import Database
from ado_sim.errors import AdoError
from ado_sim.pages import page, sessions, signin
from ado_sim.pages.board import columns
from ado_sim.process import ProjectInfo, project_info
from ado_sim.settings import Settings
from ado_sim.workitems import WorkItemStore

router = APIRouter(include_in_schema=False)
PRESESSION = "ado_sim_presession"
PARENT, CHILD = "System.LinkTypes.Hierarchy-Reverse", "System.LinkTypes.Hierarchy-Forward"


def _db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _session(request: Request) -> sessions.PageSession:
    found: sessions.PageSession = request.state.page_session
    return found


def _project(request: Request, organization: str, project: str) -> ProjectInfo | None:
    with _db(request).read() as conn:
        info = project_info(conn)
    if info is None or organization.lower() != info.organization.lower():
        return None
    if project.lower() not in (info.project.lower(), info.project_id):
        return None
    return info


def _not_found(request: Request, message: str) -> HTMLResponse:
    session = getattr(request.state, "page_session", None)
    return page(
        "error.html",
        status=404,
        heading="Not found",
        message=message,
        user=session.identity.display_name if session else None,
        csrf=session.csrf_token if session else None,
    )


def _urls(info: ProjectInfo) -> dict[str, str]:
    base = f"/{quote(info.organization)}/{quote(info.project)}"
    return {
        "board_url": f"{base}/_boards/board",
        "cards_url": f"{base}/_boards/board/cards",
        "create_url": f"{base}/_boards/board/epics",
        "item_base": f"{base}/_workitems/edit/",
    }


def _local(next_path: str | None) -> str:
    """Only a path on this site (no scheme, host or protocol-relative ``//``)."""
    if not next_path:
        return "/"
    parts = urlsplit(next_path)
    if parts.scheme or parts.netloc or not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    return next_path


# ------------------------------------------------------------------------------ sign-in


def _people(request: Request) -> list[dict[str, str]]:
    with _db(request).read() as conn:
        rows = conn.execute(
            "SELECT unique_name, display_name FROM identity WHERE is_service = 0 AND active = 1"
            " ORDER BY display_name"
        ).fetchall()
    return [{"unique_name": r[0], "display_name": r[1]} for r in rows]


def _signin_page(
    request: Request, status: int, error: str | None, chosen: str, next_path: str
) -> Response:
    token = request.cookies.get(PRESESSION) or secrets.token_urlsafe(24)
    response = page(
        "signin.html",
        status=status,
        people=_people(request),
        presession=token,
        next=_local(next_path),
        error=error,
        chosen=chosen,
    )
    response.set_cookie(
        PRESESSION,
        token,
        max_age=1800,
        httponly=True,
        samesite="lax",
        secure=_settings(request).secure_cookies,
    )
    return response


@router.get("/_signin")
def signin_form(request: Request, next: str = "/") -> Response:  # noqa: A002 - the query name
    return _signin_page(request, 200, None, "", next)


@router.post("/_signin")
def signin_submit(
    request: Request,
    unique_name: str = Form(""),
    credential: str = Form(""),
    next: str = Form("/"),  # noqa: A002
    csrf: str = Form(""),
) -> Response:
    expected = request.cookies.get(PRESESSION)
    if not expected or not sessions.csrf_ok(expected, csrf):
        return _signin_page(
            request, 403, "The form expired; please sign in again.", unique_name, next
        )
    settings = _settings(request)
    try:
        identity = signin.sign_in(
            _db(request),
            settings.token_key,
            unique_name,
            credential,
            demo_password=settings.demo_password,
        )
    except signin.SignInRefused as refused:
        request.state.log_identity = unique_name or "-"
        return _signin_page(request, 400, str(refused), unique_name, next)
    session_id = sessions.create(
        _db(request), identity, ttl_seconds=settings.page_session_ttl_seconds
    )
    response = RedirectResponse(_local(next), status_code=303)
    response.set_cookie(
        sessions.COOKIE,
        session_id,
        max_age=int(settings.page_session_ttl_seconds),
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
    )
    response.delete_cookie(PRESESSION)
    return response


@router.post("/_signout")
def signout(request: Request, csrf: str = Form("")) -> Response:
    session = _session(request)
    if not sessions.csrf_ok(session.csrf_token, csrf):
        return Response(status_code=403)
    sessions.revoke(_db(request), request.cookies.get(sessions.COOKIE))
    response = RedirectResponse("/_signin", status_code=303)
    response.delete_cookie(sessions.COOKIE)
    return response


# ------------------------------------------------------------------------------ the board


@router.get("/")
def home(request: Request) -> Response:
    with _db(request).read() as conn:
        info = project_info(conn)
    if info is None:
        return _not_found(request, "The simulator is not seeded.")
    return RedirectResponse(_urls(info)["board_url"], status_code=303)


def _board_context(
    request: Request, info: ProjectInfo, area: str | None, open_states: list[str]
) -> dict[str, Any]:
    session = _session(request)
    board = columns(_db(request), area or None)
    cards_url = _urls(info)["cards_url"] + (f"?area={quote(board.area)}" if board.area else "")
    return {
        **_urls(info),
        "cards_url": cards_url,
        "board": board,
        "project": info.project,
        "user": session.identity.display_name,
        "csrf": session.csrf_token,
        "refresh": board.settings.refresh_seconds if board.settings else None,
        "open": set(open_states),
        "form": {"title": "", "description": "", "area": board.area},
        "create_error": None,
    }


@router.get("/{organization}/{project}/_boards/board")
def board_page(request: Request, organization: str, project: str, area: str = "") -> Response:
    info = _project(request, organization, project)
    if info is None:
        return _not_found(request, f"There is no project {project} in {organization}.")
    return page("board.html", **_board_context(request, info, area, []))


@router.get("/{organization}/{project}/_boards/board/cards")
def board_cards(request: Request, organization: str, project: str, area: str = "") -> Response:
    info = _project(request, organization, project)
    if info is None:
        return _not_found(request, f"There is no project {project} in {organization}.")
    open_states = request.query_params.getlist("open")
    return page("columns.html", **_board_context(request, info, area, open_states))


@router.post("/{organization}/{project}/_boards/board/epics")
def create_item(
    request: Request,
    organization: str,
    project: str,
    title: str = Form(""),
    description: str = Form(""),
    area: str = Form(""),
    csrf: str = Form(""),
) -> Response:
    info = _project(request, organization, project)
    if info is None:
        return _not_found(request, f"There is no project {project} in {organization}.")
    session = _session(request)
    if not sessions.csrf_ok(session.csrf_token, csrf):
        return Response(status_code=403)
    context = _board_context(request, info, area, [])
    board = context["board"]
    operations: list[dict[str, Any]] = [
        {"op": "add", "path": "/fields/System.Title", "value": title}
    ]
    if description.strip():
        text = "".join(
            f"<p>{html.escape(line)}</p>" for line in description.splitlines() if line.strip()
        )
        operations.append({"op": "add", "path": "/fields/System.Description", "value": text})
    if area:
        operations.append({"op": "add", "path": "/fields/System.AreaPath", "value": area})
    try:
        store: WorkItemStore = request.app.state.store
        store.create(board.settings.type, operations, session.identity)
    except AdoError as refused:
        context.update(
            create_error=refused.message,
            form={"title": title, "description": description, "area": area},
        )
        return page("board.html", status=400, **context)
    target = _urls(info)["board_url"] + (f"?area={quote(area)}" if area else "")
    return RedirectResponse(target, status_code=303)


# ------------------------------------------------------------------------------ the item


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("displayName") or value.get("uniqueName") or "")
    if isinstance(value, list):
        return ", ".join(_text(v) for v in value)
    return "" if value is None else str(value)


@router.get("/{organization}/{project}/_workitems/edit/{item_id}")
def item_page(request: Request, organization: str, project: str, item_id: int) -> Response:
    info = _project(request, organization, project)
    store: WorkItemStore = request.app.state.store
    if info is None:
        return _not_found(request, f"There is no project {project} in {organization}.")
    try:
        item = store.get(item_id)
    except AdoError:
        return _not_found(request, f"There is no work item {item_id}.")
    with _db(request).read() as conn:
        names = {r[0]: r[1] for r in conn.execute("SELECT reference_name, name FROM field")}

    def brief(target: int) -> dict[str, Any]:
        other = store.get(target)
        return {
            "id": target,
            "type": other.fields.get("System.WorkItemType"),
            "title": other.fields.get("System.Title"),
        }

    parent = next((brief(r.target_id) for r in item.relations if r.rel == PARENT), None)
    children = [brief(r.target_id) for r in item.relations if r.rel == CHILD]
    updates = []
    for update in store.updates(item_id):
        changed = sorted(
            names.get(ref, ref) for ref in update.fields if not ref.startswith("System.Rev")
        )
        when = (update.fields.get("System.ChangedDate") or {}).get(
            "newValue"
        ) or update.revised_date
        updates.append(
            {"by": _text(update.revised_by), "when": when, "changes": ", ".join(changed) or "links"}
        )
    comments = [
        {"by": _text(c.created_by), "when": c.created_date, "text": c.text}
        for c in list_comments(store, item_id, order="asc").comments
    ]
    session = _session(request)
    urls: dict[str, Any] = dict(_urls(info))
    return page(
        "item.html",
        **urls,
        user=session.identity.display_name,
        csrf=session.csrf_token,
        item={
            "id": item.id,
            "type": item.fields.get("System.WorkItemType"),
            "title": item.fields.get("System.Title"),
            "fields": [
                (names.get(ref, ref), _text(value)) for ref, value in sorted(item.fields.items())
            ],
            "parent": parent,
            "children": children,
            "updates": updates,
            "comments": comments,
        },
    )
