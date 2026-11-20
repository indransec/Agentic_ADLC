"""The simulator's REST API: an ADO 7.1 subset (contracts/operations.md).

Every request needs a personal access token except ``GET /health`` and ``GET /openapi.json``.
Paths after ``/_apis/`` are case-insensitive, as ADO's are.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from ado_sim import __version__, auth, comments, render, schemas, wiql
from ado_sim.db import Database
from ado_sim.errors import AdoError, error_body, invalid, not_found
from ado_sim.observability import configure_logging, log_request, make_tracer
from ado_sim.process import Identity, all_fields, project_info, type_info, type_names
from ado_sim.settings import Settings
from ado_sim.workitems import ItemView, WorkItemStore

PUBLIC_PATHS = frozenset({"/health", "/openapi.json"})
MAX_BODY_BYTES = 5 * 1024 * 1024
API_VERSION = "7.1"
COMMENTS_API_VERSION = "7.1-preview.4"
MAX_HISTORY_TOP = 200
EXPANDS = ("none", "relations", "fields", "links", "all")
WIT = "/{organization}/{project}/_apis/wit"
DESCRIPTION = (
    "ADO simulator: a subset of the Azure DevOps Boards REST API 7.1 with its own data store. "
    "Authenticate with a personal access token (Basic auth with the token as password, or "
    "Bearer). Paths after /_apis/ are case-insensitive. Known differences from real ADO: "
    "contract/differences.md."
)


class CaseInsensitiveApis:
    """Lower-case the path after ``/_apis/`` before routing (ADO paths ignore case)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            index = path.find("/_apis/")
            if index >= 0:
                scope = dict(scope)
                scope["path"] = path[:index] + path[index:].lower()
        await self.app(scope, receive, send)


# ----------------------------------------------------------------- dependencies


@dataclass(frozen=True)
class Context:
    store: WorkItemStore
    urls: render.Urls
    identity: Identity


def _api_version(*supported: str) -> Any:
    def check(
        version: str | None = Query(  # noqa: B008 - FastAPI's dependency style
            None, alias="api-version", description=f"Required: {' or '.join(supported)}"
        ),
    ) -> str:
        if version is None:
            raise invalid(
                "No api-version was supplied for the request. Supported versions: "
                + ", ".join(supported),
                "VssVersionNotSpecifiedException",
            )
        if version not in supported:
            raise invalid(
                f"The requested REST API version {version} is not supported by this operation. "
                f"Supported versions: {', '.join(supported)}",
                "VssVersionOutOfRangeException",
            )
        return version

    return Depends(check)


API = _api_version(API_VERSION)
COMMENTS_API = _api_version(COMMENTS_API_VERSION)


def _project(request: Request, organization: str, project: str | None) -> render.Urls:
    db: Database = request.app.state.db
    with db.read() as conn:
        info = project_info(conn)
    if info is None or organization.lower() != info.organization.lower():
        raise not_found(
            f"The organization {organization} does not exist on this simulator.",
            "OrganizationNotFoundException",
        )
    if project is not None and project.lower() not in (info.project.lower(), info.project_id):
        raise not_found(
            f"TF200016: The following project does not exist: {project}.",
            "ProjectDoesNotExistWithNameException",
        )
    return render.Urls(
        str(request.base_url).rstrip("/"), info.organization, info.project_id, info.project
    )


def wit_context(request: Request, organization: str, project: str) -> Context:
    return Context(
        request.app.state.store, _project(request, organization, project), request.state.identity
    )


def org_urls(request: Request, organization: str) -> render.Urls:
    return _project(request, organization, None)


async def json_body(request: Request) -> Any:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise invalid("The request body is larger than 5 MB.")
    if not raw:
        raise invalid("The request needs a JSON body.")
    try:
        return json.loads(raw)
    except ValueError as error:
        raise invalid("The request body is not valid JSON.") from error


async def patch_body(request: Request) -> Any:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json-patch+json":
        raise AdoError(
            415,
            f'The request indicated a Content-Type of "{content_type or "none"}" for method type '
            f'"{request.method}" which is not supported. Valid content types for this method '
            "are: application/json-patch+json.",
            "VssRequestContentTypeNotSupportedException",
        )
    return await json_body(request)


Ctx = Annotated[Context, Depends(wit_context)]
Expand = Annotated[
    str | None, Query(alias="$expand", description="None, Relations, Fields, Links or All")
]
AsOf = Annotated[str | None, Query(alias="asOf", description="UTC date and time")]
FieldsParam = Annotated[str | None, Query(description="Comma-separated field reference names")]


def _expand(raw: str | None) -> str:
    value = (raw or "none").lower()
    if value not in EXPANDS:
        raise invalid(f"$expand must be one of None, Relations, Fields, Links, All; not {raw}.")
    return value


def _field_list(raw: Any, store: WorkItemStore) -> list[str] | None:
    if raw is None:
        return None
    names = raw if isinstance(raw, list) else str(raw).split(",")
    names = [str(name).strip() for name in names if str(name).strip()]
    known = {name.lower() for name in store.known_fields()}
    for name in names:
        if name.lower() not in known:
            raise invalid(f"TF51535: Cannot find field {name}.", "FieldNotFoundException")
    return names


def _check_fields_and_expand(only: list[str] | None, expand: str) -> None:
    if only is not None and expand != "none":
        raise invalid("The expand parameter can not be used with the fields parameter.")


def _items(
    views: list[ItemView], urls: render.Urls, only: list[str] | None, expand: str
) -> dict[str, Any]:
    return render.collection(
        [
            render.work_item(
                v,
                urls,
                only=only,
                relations=expand in ("relations", "all"),
                links=expand in ("links", "all"),
            )
            for v in views
        ]
    )


def _ids(raw: Any) -> list[int]:
    values = raw if isinstance(raw, list) else str(raw).split(",")
    try:
        ids = [int(str(value).strip()) for value in values if str(value).strip()]
    except ValueError as error:
        raise invalid("ids must be a comma-separated list of work item ids.") from error
    if not ids:
        raise invalid("At least one work item id is required.")
    return ids


def _error_policy(raw: Any) -> bool:
    value = str(raw or "fail").lower()
    if value not in ("fail", "omit"):
        raise invalid("errorPolicy must be Fail or Omit.")
    return value == "omit"


def _page(values: list[Any], top: int | None, skip: int | None) -> list[Any]:
    limit = MAX_HISTORY_TOP if top is None else top
    if not 1 <= limit <= MAX_HISTORY_TOP:
        raise invalid(f"$top must be between 1 and {MAX_HISTORY_TOP}.")
    start = skip or 0
    if start < 0:
        raise invalid("$skip cannot be negative.")
    return values[start : start + limit]


def _comment(view: comments.CommentView, urls: render.Urls) -> dict[str, Any]:
    author = render.identity_ref(view.created_by, urls)
    return {
        "workItemId": view.work_item_id,
        "id": view.id,
        "version": view.version,
        "text": view.text,
        "createdBy": author,
        "createdDate": view.created_date,
        "modifiedBy": author,
        "modifiedDate": view.modified_date,
        "isDeleted": False,
        "url": f"{urls.item(view.work_item_id)}/comments/{view.id}",
    }


def _field_ref(definition: Any, urls: render.Urls) -> dict[str, Any]:
    return {
        "referenceName": definition.reference_name,
        "name": definition.name,
        "url": urls.field(definition.reference_name),
    }


def _type(kind: Any, urls: render.Urls) -> dict[str, Any]:
    return {
        "name": kind.name,
        "referenceName": kind.reference_name,
        "description": kind.description,
        "color": kind.color,
        "isDisabled": False,
        "states": [{"name": n, "color": c, "category": cat} for n, cat, c in kind.states],
        "fields": [
            {**_field_ref(f, urls), "alwaysRequired": f.reference_name == "System.Title"}
            for f in kind.fields.values()
        ],
        "url": urls.work_item_type(kind.name),
    }


# ------------------------------------------------------------------------ app


def build_app(lifespan: Callable[[FastAPI], Any] | None = None) -> FastAPI:
    app = FastAPI(
        title="ADO simulator",
        version=__version__,
        description=DESCRIPTION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    _register_handlers(app)
    _register_routes(app)
    app.middleware("http")(_gate)
    app.add_middleware(CaseInsensitiveApis)
    app.openapi = lambda: _openapi(app)  # type: ignore[method-assign]
    return app


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_level)
    db = Database(settings.db_path, settings.busy_timeout_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        db.close()

    app = build_app(lifespan)
    app.state.db = db
    app.state.settings = settings
    app.state.store = WorkItemStore(db)
    app.state.tracer = make_tracer(settings.otlp_endpoint)
    return app


def openapi_text() -> str:
    return json.dumps(build_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def _openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            # FastAPI documents its own 422; the simulator answers invalid input with ADO's 400.
            operation.get("responses", {}).pop("422", None)
            for parameter in operation.get("parameters", []):
                if parameter["name"] == "api-version":
                    parameter["required"] = True
            if path in PUBLIC_PATHS:
                operation["security"] = []
    component_schemas = schema.setdefault("components", {}).get("schemas", {})
    for unused in ("HTTPValidationError", "ValidationError"):
        component_schemas.pop(unused, None)
    schema["components"]["securitySchemes"] = {
        "basic": {
            "type": "http",
            "scheme": "basic",
            "description": "Any user name; the personal access token as password",
        },
        "bearer": {"type": "http", "scheme": "bearer"},
    }
    schema["security"] = [{"basic": []}, {"bearer": []}]
    app.openapi_schema = schema
    return schema


async def _gate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    started = time.perf_counter()
    identity_name = "-"
    tracer = getattr(request.app.state, "tracer", None)
    span_context = tracer.start_as_current_span(f"{request.method} request") if tracer else None
    span = span_context.__enter__() if span_context is not None else None
    response: Response | None = None
    try:
        if request.method == "GET" and request.url.path in PUBLIC_PATHS:
            response = await call_next(request)
        else:
            settings: Settings = request.app.state.settings
            identity = await run_in_threadpool(
                auth.authenticate,
                request.app.state.db,
                settings.token_key,
                request.headers.get("authorization"),
            )
            length = request.headers.get("content-length", "")
            if identity is None:
                response = Response(status_code=401)
            elif length.isdigit() and int(length) > MAX_BODY_BYTES:
                identity_name = identity.unique_name
                response = JSONResponse(
                    error_body("The request body is larger than 5 MB.", "RequestTooLargeException"),
                    status_code=400,
                )
            else:
                identity_name = identity.unique_name
                request.state.identity = identity
                response = await call_next(request)
    finally:
        route = request.scope.get("route")
        operation = getattr(route, "path", "unmatched")
        status = response.status_code if response is not None else 500
        log_request(
            request.method, operation, identity_name, status, (time.perf_counter() - started) * 1000
        )
        if span is not None and span_context is not None:
            span.update_name(f"{request.method} {operation}")
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", operation)
            span.set_attribute("http.status_code", status)
            span.set_attribute("ado_sim.identity", identity_name)
            span_context.__exit__(None, None, None)
    return response


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AdoError)
    async def ado_error(_: Request, error: AdoError) -> JSONResponse:
        return JSONResponse(error.body(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        name = str(first.get("loc", ["", "request"])[-1])
        message = f"The parameter '{name}' is invalid: {first.get('msg', 'invalid value')}."
        return JSONResponse(error_body(message, "InvalidArgumentValueException"), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> Response:
        if error.status_code in (404, 405):
            body = error_body(
                f"The resource {request.url.path} with method {request.method} is not served by "
                "the ADO simulator.",
                "ResourceNotFoundException",
            )
            return JSONResponse(body, status_code=404)
        return JSONResponse(
            error_body(str(error.detail), "VssServiceException"), status_code=error.status_code
        )


def _register_routes(app: FastAPI) -> None:  # noqa: C901 - one place lists every operation
    item_response: dict[int | str, dict[str, Any]] = {200: {"model": schemas.WorkItem}}

    @app.get("/health", response_model=schemas.Health, tags=["simulator"])
    def health(request: Request) -> dict[str, str]:
        with request.app.state.db.read() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.post(
        WIT + "/workitems/${type}",
        tags=["work items"],
        summary="Create a work item",
        response_model=None,
        responses={**item_response, **schemas.ERRORS, **schemas.CONFLICT},
        openapi_extra=schemas.PATCH_BODY,
    )
    def create_work_item(
        type: str,  # noqa: A002 - ADO's parameter name
        context: Ctx,
        operations: Annotated[Any, Depends(patch_body)],
        _: Annotated[str, API],
        validate_only: Annotated[bool, Query(alias="validateOnly")] = False,
        bypass_rules: Annotated[bool, Query(alias="bypassRules")] = False,
        suppress_notifications: Annotated[bool, Query(alias="suppressNotifications")] = False,
        expand: Expand = None,
    ) -> dict[str, Any]:
        _no_bypass(bypass_rules)
        _expand(expand)
        view = context.store.create(type, operations, context.identity, validate_only=validate_only)
        return render.work_item(view, context.urls, relations=True, links=True)

    @app.get(
        WIT + "/workitems/{id}",
        tags=["work items"],
        summary="Get a work item",
        response_model=None,
        responses={**item_response, **schemas.ERRORS},
    )
    def get_work_item(
        id: int,  # noqa: A002
        context: Ctx,
        _: Annotated[str, API],
        fields: FieldsParam = None,
        as_of: AsOf = None,
        expand: Expand = None,
    ) -> dict[str, Any]:
        only = _field_list(fields, context.store)
        mode = _expand(expand)
        _check_fields_and_expand(only, mode)
        view = context.store.get(id, as_of)
        return render.work_item(
            view,
            context.urls,
            only=only,
            relations=mode in ("relations", "all"),
            links=only is None,
        )

    @app.get(
        WIT + "/workitems",
        tags=["work items"],
        summary="List work items by id (at most 200)",
        response_model=None,
        responses={200: {"model": schemas.WorkItemList}, **schemas.ERRORS},
    )
    def list_work_items(
        ids: str,
        context: Ctx,
        _: Annotated[str, API],
        fields: FieldsParam = None,
        as_of: AsOf = None,
        expand: Expand = None,
        error_policy: Annotated[
            str | None, Query(alias="errorPolicy", description="Fail or Omit")
        ] = None,
    ) -> dict[str, Any]:
        only = _field_list(fields, context.store)
        mode = _expand(expand)
        _check_fields_and_expand(only, mode)
        views = context.store.get_many(
            _ids(ids), as_of=as_of, omit_missing=_error_policy(error_policy)
        )
        return _items(views, context.urls, only, mode)

    @app.post(
        WIT + "/workitemsbatch",
        tags=["work items"],
        summary="Get work items by id in a batch (at most 200)",
        response_model=None,
        responses={200: {"model": schemas.WorkItemList}, **schemas.ERRORS},
        openapi_extra=schemas.BATCH_BODY,
    )
    def batch_work_items(
        context: Ctx, body: Annotated[Any, Depends(json_body)], _: Annotated[str, API]
    ) -> dict[str, Any]:
        if not isinstance(body, dict) or "ids" not in body:
            raise invalid("The body must be an object with ids.")
        only = _field_list(body.get("fields"), context.store)
        mode = _expand(body.get("$expand"))
        _check_fields_and_expand(only, mode)
        views = context.store.get_many(
            _ids(body["ids"]),
            as_of=body.get("asOf"),
            omit_missing=_error_policy(body.get("errorPolicy")),
        )
        return _items(views, context.urls, only, mode)

    @app.patch(
        WIT + "/workitems/{id}",
        tags=["work items"],
        summary="Update a work item with a JSON Patch document",
        response_model=None,
        responses={**item_response, **schemas.ERRORS, **schemas.CONFLICT},
        openapi_extra=schemas.PATCH_BODY,
    )
    def update_work_item(
        id: int,  # noqa: A002
        context: Ctx,
        operations: Annotated[Any, Depends(patch_body)],
        _: Annotated[str, API],
        validate_only: Annotated[bool, Query(alias="validateOnly")] = False,
        bypass_rules: Annotated[bool, Query(alias="bypassRules")] = False,
        suppress_notifications: Annotated[bool, Query(alias="suppressNotifications")] = False,
        expand: Expand = None,
    ) -> dict[str, Any]:
        _no_bypass(bypass_rules)
        _expand(expand)
        view = context.store.update(id, operations, context.identity, validate_only=validate_only)
        return render.work_item(view, context.urls, relations=True, links=True)

    @app.get(
        WIT + "/workitems/{id}/updates",
        tags=["history"],
        summary="List a work item's updates in order",
        response_model=None,
        responses={200: {"model": schemas.WorkItemUpdateList}, **schemas.ERRORS},
    )
    def list_updates(
        id: int,  # noqa: A002
        context: Ctx,
        _: Annotated[str, API],
        top: Annotated[int | None, Query(alias="$top")] = None,
        skip: Annotated[int | None, Query(alias="$skip")] = None,
    ) -> dict[str, Any]:
        updates = _page(context.store.updates(id), top, skip)
        return render.collection([render.update(u, context.urls) for u in updates])

    @app.get(
        WIT + "/workitems/{id}/updates/{updateNumber}",
        tags=["history"],
        summary="Get one update of a work item",
        response_model=None,
        responses={200: {"model": schemas.WorkItemUpdate}, **schemas.ERRORS},
    )
    def get_update(
        id: int,  # noqa: A002
        updateNumber: int,  # noqa: N803 - ADO's parameter name
        context: Ctx,
        _: Annotated[str, API],
    ) -> dict[str, Any]:
        for update in context.store.updates(id):
            if update.id == updateNumber:
                return render.update(update, context.urls)
        raise not_found(f"Work item {id} has no update {updateNumber}.")

    @app.get(
        WIT + "/workitems/{id}/revisions",
        tags=["history"],
        summary="List a work item's revisions",
        response_model=None,
        responses={200: {"model": schemas.WorkItemList}, **schemas.ERRORS},
    )
    def list_revisions(
        id: int,  # noqa: A002
        context: Ctx,
        _: Annotated[str, API],
        top: Annotated[int | None, Query(alias="$top")] = None,
        skip: Annotated[int | None, Query(alias="$skip")] = None,
        expand: Expand = None,
    ) -> dict[str, Any]:
        mode = _expand(expand)
        revisions = _page(context.store.revisions(id), top, skip)
        return render.collection(
            [
                render.work_item(
                    r,
                    context.urls,
                    relations=mode in ("relations", "all"),
                    links=mode in ("links", "all"),
                    revision_url=True,
                )
                for r in revisions
            ]
        )

    @app.get(
        WIT + "/workitems/{id}/revisions/{revisionNumber}",
        tags=["history"],
        summary="Get a work item as of one revision",
        response_model=None,
        responses={**item_response, **schemas.ERRORS},
    )
    def get_revision(
        id: int,  # noqa: A002
        revisionNumber: int,  # noqa: N803
        context: Ctx,
        _: Annotated[str, API],
        expand: Expand = None,
    ) -> dict[str, Any]:
        mode = _expand(expand)
        view = context.store.revision(id, revisionNumber)
        return render.work_item(
            view,
            context.urls,
            relations=mode in ("relations", "all"),
            links=mode in ("links", "all"),
            revision_url=True,
        )

    @app.post(
        WIT + "/wiql",
        tags=["queries"],
        summary="Query work items with the WIQL subset",
        response_model=None,
        responses={200: {"model": schemas.QueryResult}, **schemas.ERRORS},
        openapi_extra=schemas.WIQL_BODY,
    )
    def query_by_wiql(
        context: Ctx,
        body: Annotated[Any, Depends(json_body)],
        _: Annotated[str, API],
        top: Annotated[int | None, Query(alias="$top")] = None,
        time_precision: Annotated[bool, Query(alias="timePrecision")] = False,
    ) -> dict[str, Any]:
        text = body.get("query") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise invalid('The body must be {"query": "<WIQL>"}.')
        result = wiql.run_query(context.store.db, text, top=top, time_precision=time_precision)
        urls = context.urls

        def reference(item_id: int | None) -> dict[str, Any] | None:
            return None if item_id is None else {"id": item_id, "url": urls.item(item_id)}

        answer: dict[str, Any] = {
            "queryType": result.query_type,
            "queryResultType": "workItem" if result.query_type == "flat" else "workItemLink",
            "asOf": result.as_of,
            "columns": [_field_ref(c, urls) for c in result.columns],
            "sortColumns": [
                {"field": _field_ref(f, urls), "descending": d} for f, d in result.sort_columns
            ],
        }
        if result.query_type == "flat":
            answer["workItems"] = [reference(i) for i in result.work_items]
        else:
            answer["workItemRelations"] = [
                {"rel": rel, "source": reference(source), "target": reference(target)}
                for rel, source, target in result.relations
            ]
        return answer

    @app.post(
        WIT + "/workitems/{id}/comments",
        tags=["comments"],
        summary="Add a comment (api-version 7.1-preview.4)",
        response_model=None,
        responses={200: {"model": schemas.Comment}, **schemas.ERRORS},
        openapi_extra=schemas.COMMENT_BODY,
    )
    def add_comment(
        id: int,  # noqa: A002
        context: Ctx,
        body: Annotated[Any, Depends(json_body)],
        _: Annotated[str, COMMENTS_API],
    ) -> dict[str, Any]:
        text = body.get("text") if isinstance(body, dict) else None
        view = comments.add_comment(context.store, id, text, context.identity)
        return _comment(view, context.urls)

    @app.get(
        WIT + "/workitems/{id}/comments",
        tags=["comments"],
        summary="List comments (api-version 7.1-preview.4)",
        response_model=None,
        responses={200: {"model": schemas.CommentList}, **schemas.ERRORS},
    )
    def list_comments(
        id: int,  # noqa: A002
        context: Ctx,
        _: Annotated[str, COMMENTS_API],
        top: Annotated[int | None, Query(alias="$top")] = None,
        continuation_token: Annotated[str | None, Query(alias="continuationToken")] = None,
        order: Annotated[str, Query(description="asc or desc (default desc)")] = "desc",
        include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
        expand: Annotated[str | None, Query(alias="$expand")] = None,
    ) -> dict[str, Any]:
        page = comments.list_comments(
            context.store, id, top=top, continuation=continuation_token, order=order
        )
        answer: dict[str, Any] = {
            "totalCount": page.total,
            "count": len(page.comments),
            "comments": [_comment(c, context.urls) for c in page.comments],
        }
        if page.continuation:
            answer["nextPage"] = (
                f"{context.urls.item(id)}/comments?continuationToken={page.continuation}"
                f"&order={order.lower()}&api-version={COMMENTS_API_VERSION}"
            )
            answer["continuationToken"] = page.continuation
        return answer

    @app.get(
        WIT + "/workitemtypes",
        tags=["process"],
        summary="List work item types",
        response_model=None,
        responses={200: {"model": schemas.WorkItemTypeList}, **schemas.ERRORS},
    )
    def list_types(context: Ctx, _: Annotated[str, API]) -> dict[str, Any]:
        with context.store.db.read() as conn:
            kinds = [type_info(conn, name) for name in type_names(conn)]
        return render.collection([_type(k, context.urls) for k in kinds if k is not None])

    @app.get(
        WIT + "/workitemtypes/{type}",
        tags=["process"],
        summary="Get a work item type",
        response_model=None,
        responses={200: {"model": schemas.WorkItemType}, **schemas.ERRORS},
    )
    def get_type(
        type: str,  # noqa: A002
        context: Ctx,
        _: Annotated[str, API],
    ) -> dict[str, Any]:
        return _type(_known_type(context, type), context.urls)

    @app.get(
        WIT + "/workitemtypes/{type}/states",
        tags=["process"],
        summary="List the states of a work item type",
        response_model=None,
        responses={200: {"model": schemas.StateList}, **schemas.ERRORS},
    )
    def list_states(
        type: str,  # noqa: A002
        context: Ctx,
        _: Annotated[str, API],
    ) -> dict[str, Any]:
        kind = _known_type(context, type)
        return render.collection(
            [{"name": n, "color": c, "category": cat} for n, cat, c in kind.states]
        )

    @app.get(
        WIT + "/fields",
        tags=["process"],
        summary="List fields",
        response_model=None,
        responses={200: {"model": schemas.WorkItemFieldList}, **schemas.ERRORS},
    )
    def list_fields(context: Ctx, _: Annotated[str, API]) -> dict[str, Any]:
        with context.store.db.read() as conn:
            definitions = list(all_fields(conn).values())
        return render.collection(
            [
                {
                    **_field_ref(f, context.urls),
                    "type": f.type,
                    "readOnly": f.read_only,
                    "usage": "workItem",
                    "isIdentity": f.type == "identity",
                }
                for f in definitions
            ]
        )

    @app.get(
        WIT + "/classificationnodes/areas",
        tags=["process"],
        summary="Get the area tree",
        response_model=None,
        responses={200: {"model": schemas.ClassificationNode}, **schemas.ERRORS},
    )
    def get_areas(
        context: Ctx,
        _: Annotated[str, API],
        depth: Annotated[int, Query(alias="$depth", ge=0)] = 0,
    ) -> dict[str, Any]:
        with context.store.db.read() as conn:
            nodes = [dict(r) for r in conn.execute("SELECT * FROM area_node ORDER BY id")]
        return _area_tree(nodes, context.urls, depth)

    @app.get(
        "/{organization}/_apis/identities",
        tags=["identities"],
        summary="Read identities by unique or display name, or by id",
        response_model=None,
        responses={200: {"model": schemas.IdentityList}, **schemas.ERRORS},
    )
    def read_identities(
        request: Request,
        organization: str,
        _: Annotated[str, API],
        search_filter: Annotated[str | None, Query(alias="searchFilter")] = None,
        filter_value: Annotated[str | None, Query(alias="filterValue")] = None,
        identity_ids: Annotated[str | None, Query(alias="identityIds")] = None,
        query_membership: Annotated[str | None, Query(alias="queryMembership")] = None,
    ) -> dict[str, Any]:
        org_urls(request, organization)
        db: Database = request.app.state.db
        with db.read() as conn:
            if identity_ids:
                wanted = [i.strip().replace("-", "").lower() for i in identity_ids.split(",")]
                rows = [
                    r
                    for r in conn.execute("SELECT * FROM identity ORDER BY unique_name")
                    if r["id"].replace("-", "").lower() in wanted
                ]
            elif search_filter is not None and filter_value is not None:
                if search_filter.lower() not in (
                    "general",
                    "accountname",
                    "mailaddress",
                    "displayname",
                ):
                    raise invalid(f"searchFilter {search_filter} is not supported.")
                rows = conn.execute(
                    "SELECT * FROM identity WHERE unique_name = ? COLLATE NOCASE"
                    " OR display_name = ? COLLATE NOCASE ORDER BY unique_name",
                    (filter_value, filter_value),
                ).fetchall()
            else:
                raise invalid("Give identityIds, or searchFilter with filterValue.")
        return render.collection([_identity(r) for r in rows])


def _identity(row: Any) -> dict[str, Any]:
    text = {"$type": "System.String"}
    return {
        "id": row["id"],
        "descriptor": "Microsoft.IdentityModel.Claims.ClaimsIdentity;ado-sim\\"
        + row["unique_name"],
        "subjectDescriptor": f"sim.{row['id']}",
        "providerDisplayName": row["display_name"],
        "isActive": bool(row["active"]),
        "isContainer": False,
        "members": [],
        "memberOf": [],
        "memberIds": [],
        "properties": {
            "SchemaClassName": {**text, "$value": "User"},
            "Account": {**text, "$value": row["unique_name"]},
            "Mail": {**text, "$value": row["unique_name"]},
        },
        "resourceVersion": 2,
        "metaTypeId": 0,
    }


def _area_tree(nodes: list[dict[str, Any]], urls: render.Urls, depth: int) -> dict[str, Any]:
    children: dict[int | None, list[dict[str, Any]]] = {}
    for node in nodes:
        children.setdefault(node["parent_id"], []).append(node)

    def build(node: dict[str, Any], remaining: int) -> dict[str, Any]:
        below = children.get(node["id"], [])
        relative = node["path"].split("\\", 1)[1] if "\\" in node["path"] else ""
        path = "\\" + urls.project + "\\Area" + (("\\" + relative) if relative else "")
        body: dict[str, Any] = {
            "id": node["id"],
            "identifier": node["identifier"],
            "name": node["name"],
            "structureType": "area",
            "hasChildren": bool(below),
            "path": path,
        }
        if remaining > 0 and below:
            body["children"] = [build(child, remaining - 1) for child in below]
        body["url"] = f"{urls.wit}/classificationNodes/Areas" + (
            "/" + "/".join(quote(part) for part in relative.split("\\")) if relative else ""
        )
        return body

    return build(children[None][0], depth)


def _known_type(context: Context, name: str) -> Any:
    with context.store.db.read() as conn:
        kind = type_info(conn, name)
    if kind is None:
        raise not_found(
            f"TF201083: Work item type {name} does not exist.", "WorkItemTypeNotFoundException"
        )
    return kind


def _no_bypass(bypass_rules: bool) -> None:
    if bypass_rules:
        raise invalid("bypassRules is not supported: the simulator has no rules to bypass.")
