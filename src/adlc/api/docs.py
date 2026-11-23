"""What every platform operation is for, who may call it and how it can refuse (022).

Applied to the OpenAPI document as it is generated (:func:`document`), so the document, the web
application's generated types and ``docs/api-reference.md`` (``make api-docs``) all say the same.
Every operation must have an entry here: generating the document fails on an undocumented one,
so a new operation cannot ship without its contract (``tests/unit/api/test_openapi_fresh.py``).

Errors are declared per operation in the platform's own shape (:class:`ErrorBody`). Three are
added where they always apply: 401 on every operation that needs a session, 403 ("cross-site
request refused") on every changing operation (a cookie session without its CSRF value), and 422
on every operation that takes parameters or a body.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from adlc.api.auth import PUBLIC_PATHS
from adlc.api.schemas.base import ErrorBody

ERRORS: dict[int, str] = {
    401: "`not_signed_in`: no session, or it expired or was revoked",
    403: "`not_allowed`: the person may not do this (or a cookie session's change came without "
    "its CSRF value)",
    404: "`not_found`: no such use case, run, request, event or file",
    409: "`stale` (the run changed since the version sent) or `wrong_state` (not possible in the "
    "current state, or already decided)",
    422: "`invalid`: the input was refused; `field` names it when one field is at fault",
}
ERROR_REF = "#/components/schemas/ErrorBody"
SUCCESS = {"200": "OK", "201": "Created", "204": "Done; no body"}
# Path parameters, the same wherever they appear
PATH_PARAMETERS: dict[str, str] = {
    "run_id": "A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`)",
    "usecase_id": "A use case, such as `UC-0001`",
    "artifact_id": "An artifact id of the run's terminal spec, such as `kpis`",
    "content_hash": "The attachment's SHA-256, from the artifact's `attachments`",
    "clarification_id": "A clarification: `<run id>/clar-<n>` (contains `/`)",
    "waiver_id": "A waiver, such as `WVR-0001`",
    "event_id": "The event's id (a dead letter's UUID, or a proposed event's id in its artifact)",
    "change_id": "A change request, such as `CHG-1`",
    "terminal_id": "A terminal id from the pinned specs, `T<n>`",
    "run_number": "The run's last part, such as `run-1`",
}

TAGS: list[dict[str, str]] = [
    {"name": "Health", "description": "Is the API up and can it reach its database."},
    {
        "name": "Sessions",
        "description": "Sign in (a bearer token, or the browser's HttpOnly cookie), who is "
        "signed in, sign out.",
    },
    {
        "name": "Use cases",
        "description": "Submit a use case, list them, follow one, verify its evidence ledger.",
    },
    {"name": "Inbox", "description": "Everything waiting for the signed-in person."},
    {"name": "Runs", "description": "A terminal run's detail and the decisions people take on it."},
    {
        "name": "Artifacts",
        "description": "Edit a run's artifacts, upload spreadsheets, attach and download files, "
        "see versions.",
    },
    {"name": "Requests", "description": "Clarifications, waivers and dead-lettered events."},
    {
        "name": "Changes",
        "description": "Change requests waiting for the ITSM approver (feature 012).",
    },
    {
        "name": "Proposed events",
        "description": "Lifecycle events an agent proposed, waiting for a person (feature 012).",
    },
    {
        "name": "Dashboard",
        "description": "Read-only views over the platform's records (feature 013).",
    },
]


@dataclass(frozen=True)
class Doc:
    tag: str
    summary: str
    description: str
    errors: tuple[int, ...] = ()


ANY = "Any signed-in person."
ENDPOINTS: dict[tuple[str, str], Doc] = {
    ("GET", "/health"): Doc(
        "Health",
        "Service health",
        "Public. `200` with every check `ok`, or `503` with the failing check `unavailable`.",
        (503,),
    ),
    ("POST", "/auth/sign-in"): Doc(
        "Sessions",
        "Sign in",
        'Public. With `session` omitted or `"bearer"`, answers a bearer token for the '
        '`Authorization` header (tools, tests, pilot processes). With `"cookie"` (the browser '
        "application) the request must carry `X-ADLC-CSRF: sign-in`; the answer sets the HttpOnly, "
        "SameSite=Strict cookie `adlc_session` and carries the session's CSRF value instead of the "
        "token. A wrong account or password answers `401` without saying which.",
        (401,),
    ),
    ("POST", "/auth/sign-out"): Doc(
        "Sessions",
        "Sign out",
        "Revokes the session. For a cookie session the answer also clears the cookie.",
    ),
    ("GET", "/auth/me"): Doc(
        "Sessions",
        "Who is signed in",
        f"{ANY} The person's account, name and roles; for a cookie session also `csrf_token`, the "
        "value every changing request must send in `X-ADLC-CSRF`.",
    ),
    ("POST", "/usecases"): Doc(
        "Use cases",
        "Submit a use case",
        "A person in a role allowed to submit (the role catalogue's submitters; anyone when none "
        "is configured). Pins the active terminal specs and opens the first terminal's run.",
        (403, 409),
    ),
    ("GET", "/usecases"): Doc(
        "Use cases",
        "List use cases",
        f"{ANY} Newest first, with each one's count of open runs. `mine=true`: those the person "
        "submitted or takes part in through a role of one of its runs.",
    ),
    ("GET", "/usecases/{usecase_id}"): Doc(
        "Use cases",
        "A use case's journey",
        f"{ANY} The use case, all its runs, per-terminal time and rework summary, and model cost.",
        (404,),
    ),
    ("POST", "/usecases/{usecase_id}/verify"): Doc(
        "Use cases",
        "Verify the use case's evidence ledger",
        f"{ANY} Re-computes the hash chain of the use case's ledger records and lists any break. "
        "The verification is itself recorded, under the person.",
        (404,),
    ),
    ("GET", "/inbox"): Doc(
        "Inbox",
        "What is waiting for me",
        f"{ANY} Sign-offs, clarifications, escalations, waivers and blocked runs addressed to one "
        "of the person's roles (and dead letters for the CoE role), soonest due first.",
    ),
    ("GET", "/runs/{run_id}"): Doc(
        "Runs",
        "A run's detail and decision form",
        f"{ANY} Everything SA §8.2 asks for on one page: the run, its artifacts and versions, "
        "prerequisites, control results, the reviewer's recommendation, prior rework, "
        "clarifications, approvals, waiver, timer, cost, timeline and evidence; and `form`, what "
        "this person may decide and what each outcome needs (built from the pinned spec).",
        (404,),
    ),
    ("POST", "/runs/{run_id}/decisions"): Doc(
        "Runs",
        "Decide on a run",
        "A person in a sign-off role of the run (the spec's status rights); `terminate` also for "
        "the roles the spec allows to terminate. Sends `expected_version`, the version the person "
        "saw. `rework` needs `root_cause` (and `target_terminal` where the cause's route resolves "
        "a terminal); `exception` needs the spec's waiver fields and opens a waiver; `pass` needs "
        "the emitted values the spec asks people to type. A decision that differs from the "
        "reviewer's recommendation needs a `reason`. Rights are checked on every decision.",
        (403, 404, 409),
    ),
    ("POST", "/runs/{run_id}/escalation"): Doc(
        "Runs",
        "Complete an escalated run",
        "A person in one of the terminal's accountable roles, while the run is escalated. Supplies "
        "the artifacts the agents could not finish; the run then goes to normal sign-off. Sends "
        "`expected_version`.",
        (403, 404, 409),
    ),
    ("PUT", "/runs/{run_id}/artifacts/{artifact_id}"): Doc(
        "Artifacts",
        "Edit an artifact",
        "A person in a sign-off or accountable role of the run, while it awaits sign-off or is "
        "escalated. Replaces the artifact's rows with a new version (the run's controls re-run); "
        "`changed` is false when the rows were identical. Sends `expected_version`.",
        (403, 404, 409),
    ),
    ("POST", "/runs/{run_id}/artifacts/{artifact_id}/spreadsheet"): Doc(
        "Artifacts",
        "Replace a table from a spreadsheet",
        "Same rights as editing. A multipart `.xlsx` upload (`file`, `expected_version`); its rows "
        "become the artifact's new version.",
        (403, 404, 409),
    ),
    ("POST", "/runs/{run_id}/artifacts/{artifact_id}/attachments"): Doc(
        "Artifacts",
        "Attach a file to an artifact",
        "Same rights as editing. A multipart upload (`file`, `expected_version`) of an allowed "
        "type (`ADLC_ATTACHMENT_TYPES`) and size (`ADLC_ATTACHMENT_MAX`), stored "
        "content-addressed with the artifact's current version. The file name is reduced to its "
        "last path segment.",
        (403, 404, 409),
    ),
    ("GET", "/runs/{run_id}/artifacts/{artifact_id}/history"): Doc(
        "Artifacts",
        "An artifact's versions",
        f"{ANY} Every version of the artifact on this run: who produced it, when, its hash, the "
        "version it was derived from, and its attachments.",
        (404,),
    ),
    ("GET", "/runs/{run_id}/attachments/{content_hash}"): Doc(
        "Artifacts",
        "Download an attachment",
        f"{ANY} Only an attachment recorded on this run. Always a download: `Content-Disposition: "
        "attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src "
        "'none'; sandbox`, `Cache-Control: private, no-store`.",
        (404,),
    ),
    ("POST", "/clarifications/{clarification_id}/answers"): Doc(
        "Requests",
        "Answer a clarification",
        "A person in the role the agent addressed. One answer per question; the same run resumes "
        "(it does not count as rework). Answered once.",
        (403, 404, 409),
    ),
    ("POST", "/waivers/{waiver_id}/decision"): Doc(
        "Requests",
        "Approve or reject a waiver",
        "A person in a role allowed to set the exception (or the terminal's accountable roles), "
        "and not the person who proposed it. Approval closes the run as an exception; rejection "
        "returns it to sign-off.",
        (403, 404, 409),
    ),
    ("GET", "/dead-letters"): Doc(
        "Requests",
        "List dead-lettered events",
        "The CoE role (`ADLC_DEADLETTER_ROLE`). Events the router could not deliver after its "
        "retries, with attempts, last error and how often each was re-queued.",
        (403,),
    ),
    ("GET", "/dead-letters/{event_id}"): Doc(
        "Requests",
        "A dead letter's payload and history",
        "The CoE role. The event's payload and its re-queue history.",
        (403, 404),
    ),
    ("POST", "/dead-letters/{event_id}/requeue"): Doc(
        "Requests",
        "Re-queue a dead letter",
        "The CoE role. Puts the event back in the outbox for delivery and records who did it.",
        (403, 404),
    ),
    ("GET", "/changes"): Doc(
        "Changes",
        "Change requests waiting for a decision",
        "The ITSM approver role named in the tool registry; empty for anyone else.",
    ),
    ("POST", "/changes/{change_id}/decision"): Doc(
        "Changes",
        "Approve or reject a change request",
        "The ITSM approver role. Records the decision as a new version of the change record; runs "
        "whose controls wait for it re-run them.",
        (403, 404, 409),
    ),
    ("GET", "/events/proposed"): Doc(
        "Proposed events",
        "Proposed events waiting for me",
        "Events an agent proposed in a run's artifact, for a person in the terminal's accountable "
        "roles; empty for anyone else.",
    ),
    ("POST", "/events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}"): Doc(
        "Proposed events",
        "Confirm or dismiss a proposed event",
        "A person in the terminal's accountable roles. Confirming raises the event (and its route "
        "runs); dismissing records it. Each proposal is decided once. The run is named by its "
        "three parts (`UC-0001`, `T<n>`, `run-1`).",
        (403, 404, 409),
    ),
    ("GET", "/dashboard/usecases/{usecase_id}/journey"): Doc(
        "Dashboard",
        "A use case's journey view",
        f"{ANY} Lanes per pinned terminal with a bar per run, arrows for reworks, reroutes, "
        "exceptions, events and re-entry with their causes, and the escalations and exceptions "
        "panel.",
        (404,),
    ),
    ("GET", "/dashboard/usecases/{usecase_id}/kpis"): Doc(
        "Dashboard",
        "A use case's KPIs",
        f"{ANY} Every KPI with its definition and value (`null` where it is not yet defined).",
        (404,),
    ),
    ("GET", "/dashboard/portfolio"): Doc(
        "Dashboard",
        "KPIs across use cases",
        f"{ANY} Counts and times summed, rates pooled; filter by `risk_tier` and `status`.",
    ),
    ("GET", "/dashboard/activity"): Doc(
        "Dashboard",
        "The activity feed",
        f"{ANY} What agents, reviewers, people and the orchestrator did, newest first; filter by "
        "`usecase_id`, `terminal_id`, `actor_type` and `step`; `limit` 1 to 1000 (default 200).",
    ),
    ("GET", "/dashboard/runs/{run_id}/timeline"): Doc(
        "Dashboard",
        "A run's step timeline",
        f"{ANY} Each step with its duration, and each agent attempt with its model and tool calls.",
        (404,),
    ),
}


def _errors(path: str, method: str, operation: dict[str, Any], doc: Doc) -> set[int]:
    found = set(doc.errors) - {503}  # 503 (health) is declared on its route
    if path not in PUBLIC_PATHS:
        found.add(401)
    if method not in ("GET", "HEAD", "OPTIONS"):
        found.add(403)  # a cookie session's change without its CSRF value
    if operation.get("parameters") or operation.get("requestBody"):
        found.add(422)
    return found


def apply(schema: dict[str, Any]) -> None:
    """Document every operation of a generated OpenAPI document, in place."""
    undocumented = []
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            doc = ENDPOINTS.get((method.upper(), path))
            if doc is None:
                undocumented.append(f"{method.upper()} {path}")
                continue
            operation["summary"] = doc.summary
            operation["description"] = doc.description
            operation["tags"] = [doc.tag]
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "path" and not parameter.get("description"):
                    parameter["description"] = PATH_PARAMETERS.get(parameter["name"], "")
            errors = _errors(path, method.upper(), operation, doc)
            responses = {
                status: answer
                for status, answer in operation.get("responses", {}).items()
                if int(status) < 400 or int(status) == 503
            }
            for status, answer in responses.items():
                if status in SUCCESS and answer.get("description") in (
                    "Successful Response",
                    "",
                    None,
                ):
                    answer["description"] = SUCCESS[status]
            for status in sorted(errors):
                responses[str(status)] = {
                    "description": ERRORS[status],
                    "content": {"application/json": {"schema": {"$ref": ERROR_REF}}},
                }
            operation["responses"] = responses
    if undocumented:
        raise RuntimeError(
            f"undocumented API operations (add them to adlc.api.docs): {undocumented}"
        )
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["ErrorBody"] = ErrorBody.model_json_schema(ref_template="#/components/schemas/{model}")
    for unused in ("HTTPValidationError", "ValidationError"):  # FastAPI's, never answered here
        schemas.pop(unused, None)
    schema["tags"] = TAGS


def document(app: FastAPI) -> None:
    """Generate the app's OpenAPI document with every operation's contract applied."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes, tags=TAGS)
            apply(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
