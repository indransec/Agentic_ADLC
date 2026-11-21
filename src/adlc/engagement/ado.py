"""The ADO REST 7.1 adapter (contracts/board-port.md; research R-01).

The only module that knows Azure DevOps' shapes: paths, JSON Patch, WIQL, the ``System.*``
protocol fields an item always carries (type, revision, changer, team project, changed date) and
the hierarchy link type. Everything the platform names on the board (types, states, the fields
it writes and reads) arrives as data from the tracker mapping. It talks to the simulator of
feature 015 exactly as it would to ``dev.azure.com``.

Errors carry status codes and ADO type keys, never field values or the token.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from adlc.engagement.model import (
    BoardInfo,
    BoardItem,
    BoardType,
    BoardUpdate,
    ChangePage,
    FieldChange,
    Identity,
    ItemWrite,
)
from adlc.engagement.port import (
    BoardAuthFailed,
    BoardError,
    BoardRefused,
    BoardUnreachable,
    ItemNotFound,
    RevisionConflict,
)

API = "7.1"
COMMENTS_API = "7.1-preview.4"
PATCH_TYPE = "application/json-patch+json"
PAGE = 200
TIMEOUT_S = 10.0
# ADO protocol: the fields every item carries and the hierarchy link, not platform names.
TYPE_FIELD = "System.WorkItemType"
CHANGED_BY = "System.ChangedBy"
PARENT = "System.LinkTypes.Hierarchy-Reverse"
_WIQL = (
    "SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @project{since}"
    " ORDER BY [System.ChangedDate] ASC, [System.Id] ASC"
)


class AdoBoard:
    def __init__(
        self,
        *,
        base_url: str,
        organization: str,
        project: str,
        token: str,
        identities_url: str | None = None,
        public_url: str | None = None,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._org_url = f"{base_url.rstrip('/')}/{quote(organization)}"
        self._wit = f"{self._org_url}/{quote(project)}/_apis/wit"
        # 019: the board's address for browsers (inside Docker the sync uses the service name)
        public = (public_url or base_url).rstrip("/")
        self._edit = f"{public}/{quote(organization)}/{quote(project)}/_workitems/edit"
        self._identities = f"{(identities_url or base_url).rstrip('/')}/{quote(organization)}"
        credentials = base64.b64encode(f":{token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {credentials}"}
        self._client = client or httpx.Client(timeout=timeout_s)

    def __repr__(self) -> str:  # never show the token
        return f"AdoBoard({self._wit!r})"

    # ------------------------------------------------------------------ port

    def item_url(self, item_id: int) -> str:
        return f"{self._edit}/{item_id}"

    def check(self) -> BoardInfo:
        kinds = self._call("GET", f"{self._wit}/workitemtypes")["value"]
        types = {
            k["name"]: BoardType(
                k["name"],
                tuple(s["name"] for s in k.get("states", [])),
                frozenset(f["referenceName"] for f in k.get("fields", [])),
            )
            for k in kinds
        }
        tree = self._call("GET", f"{self._wit}/classificationnodes/Areas", {"$depth": "20"})
        return BoardInfo(types=types, areas=frozenset(_area_paths(tree)))

    def create(
        self, item_type: str, fields: Mapping[str, Any], parent_id: int | None = None
    ) -> BoardItem:
        operations: list[dict[str, Any]] = [
            {"op": "add", "path": f"/fields/{name}", "value": value}
            for name, value in fields.items()
            if value not in (None, "")
        ]
        if parent_id is not None:
            operations.append(
                {
                    "op": "add",
                    "path": "/relations/-",
                    "value": {"rel": PARENT, "url": self._item_url(parent_id)},
                }
            )
        body = self._call(
            "POST",
            f"{self._wit}/workitems/${quote(item_type)}",
            {"$expand": "Relations"},
            json_body=operations,
            patch=True,
        )
        return _item(body)

    def get(self, item_id: int) -> BoardItem:
        return _item(
            self._call("GET", f"{self._wit}/workitems/{item_id}", {"$expand": "Relations"})
        )

    def get_at(self, item_id: int, rev: int) -> BoardItem:
        return _item(
            self._call(
                "GET",
                f"{self._wit}/workitems/{item_id}/revisions/{rev}",
                {"$expand": "Relations"},
            )
        )

    def update(self, item_id: int, write: ItemWrite) -> BoardItem:
        operations: list[dict[str, Any]] = []
        if write.expected_rev is not None:
            operations.append({"op": "test", "path": "/rev", "value": write.expected_rev})
        operations += [
            {"op": "add", "path": f"/fields/{name}", "value": value}
            for name, value in write.set.items()
            if value not in (None, "")
        ]
        operations += [
            {"op": "remove", "path": f"/fields/{name}"}
            for name in (*write.clear, *(n for n, v in write.set.items() if v in (None, "")))
        ]
        body = self._call(
            "PATCH",
            f"{self._wit}/workitems/{item_id}",
            {"$expand": "Relations"},
            json_body=operations,
            patch=True,
        )
        return _item(body)

    def comment(self, item_id: int, text: str) -> None:
        self._call(
            "POST",
            f"{self._wit}/workitems/{item_id}/comments",
            {"api-version": COMMENTS_API},
            json_body={"text": text},
        )

    def changed_since(self, watermark: str | None) -> ChangePage:
        since = "" if watermark is None else f" AND [System.ChangedDate] >= '{_quote(watermark)}'"
        body = self._call(
            "POST",
            f"{self._wit}/wiql",
            {"timePrecision": "true"},
            json_body={"query": _WIQL.format(since=since)},
        )
        ids = tuple(int(w["id"]) for w in body.get("workItems", []))
        return ChangePage(ids, str(body["asOf"]))

    def updates(self, item_id: int, after_update_id: int = 0) -> list[BoardUpdate]:
        found: list[BoardUpdate] = []
        skip = 0
        while True:
            page = self._call(
                "GET",
                f"{self._wit}/workitems/{item_id}/updates",
                {"$top": str(PAGE), "$skip": str(skip)},
            )["value"]
            found += [_update(u) for u in page if int(u["id"]) > after_update_id]
            if len(page) < PAGE:
                return found
            skip += PAGE

    def find_identity(self, unique_name: str) -> Identity | None:
        body = self._call(
            "GET",
            f"{self._identities}/_apis/identities",
            {"searchFilter": "General", "filterValue": unique_name},
        )
        for entry in body.get("value", []):
            account = str(entry.get("properties", {}).get("Account", {}).get("$value", ""))
            if account.lower() == unique_name.lower():
                return Identity(
                    account.lower(), str(entry.get("providerDisplayName", "")), str(entry["id"])
                )
        return None

    # ------------------------------------------------------------------ transport

    def _item_url(self, item_id: int) -> str:
        return f"{self._org_url}/_apis/wit/workItems/{item_id}"

    def _call(
        self,
        method: str,
        url: str,
        params: Mapping[str, str] | None = None,
        *,
        json_body: Any = None,
        patch: bool = False,
    ) -> Any:
        query = {"api-version": API, **(params or {})}
        headers = dict(self._headers)
        if json_body is not None:
            headers["Content-Type"] = PATCH_TYPE if patch else "application/json"
        content = None if json_body is None else json.dumps(json_body).encode()
        response = None
        for attempt in (1, 2):
            try:
                response = self._client.request(
                    method, url, params=query, headers=headers, content=content
                )
            except httpx.TransportError as error:
                if attempt == 2:
                    raise BoardUnreachable(
                        f"{method} {_route(url)}: {type(error).__name__}"
                    ) from None
                continue
            if response.status_code >= 500 and attempt == 1:
                continue
            break
        assert response is not None  # noqa: S101 - the loop always sets it or raises
        return _answer(method, url, response)


def _answer(method: str, url: str, response: httpx.Response) -> Any:
    status = response.status_code
    if status < 300:
        return response.json() if response.content else None
    where = f"{method} {_route(url)}"
    if status == 401:
        raise BoardAuthFailed(f"{where}: the board refused the token")
    key = _type_key(response)
    if status == 404:
        raise ItemNotFound(f"{where}: not found ({key})")
    if status == 412:
        raise RevisionConflict(f"{where}: the item changed since it was read ({key})")
    if status >= 500:
        raise BoardUnreachable(f"{where}: board error {status}")
    if status in (400, 409, 415):
        raise BoardRefused(f"{where}: refused {status} ({key})")
    raise BoardError(f"{where}: unexpected status {status}")


def _type_key(response: httpx.Response) -> str:
    try:
        return str(response.json().get("typeKey", "unknown"))
    except ValueError:
        return "unknown"


def _route(url: str) -> str:
    """The path after ``_apis`` (no host, organisation or ids' values beyond the route)."""
    return url.split("/_apis", 1)[-1]


def _quote(text: str) -> str:
    return text.replace("'", "''")


def _parent(body: Mapping[str, Any]) -> int | None:
    for relation in body.get("relations") or []:
        if relation.get("rel") == PARENT:
            return int(str(relation["url"]).rstrip("/").rsplit("/", 1)[-1])
    return None


def _identity_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        name = value.get("uniqueName")
        return None if name is None else str(name).lower()
    return None


def _item(body: Mapping[str, Any]) -> BoardItem:
    fields = dict(body.get("fields", {}))
    return BoardItem(
        id=int(body["id"]),
        rev=int(body["rev"]),
        type=str(fields.get(TYPE_FIELD, "")),
        fields=fields,
        parent_id=_parent(body),
        changed_by=_identity_name(fields.get(CHANGED_BY)),
    )


def _update(body: Mapping[str, Any]) -> BoardUpdate:
    fields = {
        name: FieldChange(change.get("oldValue"), change.get("newValue"))
        for name, change in (body.get("fields") or {}).items()
    }
    relations = body.get("relations") or {}

    def parent_of(entries: Any) -> int | None:
        for relation in entries or []:
            if relation.get("rel") == PARENT:
                return int(str(relation["url"]).rstrip("/").rsplit("/", 1)[-1])
        return None

    return BoardUpdate(
        item_id=int(body["workItemId"]),
        update_id=int(body["id"]),
        rev=int(body["rev"]),
        changed_by=_identity_name(body.get("revisedBy")) or "",
        fields=fields,
        parent_added=parent_of(relations.get("added")),
        parent_removed=parent_of(relations.get("removed")),
    )


def _area_paths(node: Mapping[str, Any], prefix: str = "") -> list[str]:
    path = f"{prefix}\\{node['name']}" if prefix else str(node["name"])
    found = [path]
    for child in node.get("children") or []:
        found += _area_paths(child, path)
    return found
