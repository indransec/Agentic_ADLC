"""JSON shapes of the ADO REST API 7.1 subset (contracts/operations.md).

Stored values hold ids; URLs are built here from the request's base URL, so the same data
renders correctly whatever host name a client uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from ado_sim.patch import RELATION_TYPES, Relation
from ado_sim.workitems import ItemView, UpdateView


@dataclass(frozen=True)
class Urls:
    base: str
    organization: str
    project_id: str
    project: str

    @property
    def org(self) -> str:
        return f"{self.base}/{quote(self.organization)}"

    @property
    def wit(self) -> str:
        return f"{self.org}/{self.project_id}/_apis/wit"

    def item(self, item_id: int) -> str:
        return f"{self.wit}/workItems/{item_id}"

    def link_target(self, item_id: int) -> str:
        return f"{self.org}/_apis/wit/workItems/{item_id}"

    def identity(self, identity_id: str) -> str:
        return f"{self.org}/_apis/identities/{identity_id}"

    def field(self, reference_name: str) -> str:
        return f"{self.wit}/fields/{reference_name}"

    def work_item_type(self, name: str) -> str:
        return f"{self.wit}/workItemTypes/{quote(name)}"


def identity_ref(value: dict[str, Any], urls: Urls, *, with_name: bool = False) -> dict[str, Any]:
    identity_id = value["id"]
    rendered = {
        "displayName": value["displayName"],
        "url": urls.identity(identity_id),
        "_links": {
            "avatar": {"href": f"{urls.org}/_apis/GraphProfile/MemberAvatars/{identity_id}"}
        },
        "id": identity_id,
        "uniqueName": value["uniqueName"],
        "imageUrl": f"{urls.org}/_api/_common/identityImage?id={identity_id}",
        "descriptor": f"sim.{identity_id}",
    }
    if with_name:
        rendered["name"] = f"{value['displayName']} <{value['uniqueName']}>"
    return rendered


def _value(value: Any, urls: Urls) -> Any:
    if isinstance(value, dict) and "uniqueName" in value and "id" in value:
        return identity_ref(value, urls)
    return value


def fields(values: dict[str, Any], urls: Urls, only: list[str] | None = None) -> dict[str, Any]:
    if only is not None:
        wanted = {name.lower() for name in only}
        values = {k: v for k, v in values.items() if k.lower() in wanted}
    return {ref: _value(value, urls) for ref, value in values.items()}


def relation(item: Relation, urls: Urls, *, with_name: bool = True) -> dict[str, Any]:
    attributes = dict(item.attributes)
    if with_name:
        attributes["name"] = RELATION_TYPES[item.rel][1]
    return {"rel": item.rel, "url": urls.link_target(item.target_id), "attributes": attributes}


def _stored_relation(data: dict[str, Any], urls: Urls) -> dict[str, Any]:
    return relation(Relation.from_stored(data), urls, with_name=False)


def work_item_links(item_id: int, kind: str, urls: Urls) -> dict[str, Any]:
    url = urls.item(item_id)
    return {
        "self": {"href": url},
        "workItemUpdates": {"href": f"{url}/updates"},
        "workItemRevisions": {"href": f"{url}/revisions"},
        "workItemComments": {"href": f"{url}/comments"},
        "html": {"href": f"{urls.org}/{quote(urls.project)}/_workitems/edit/{item_id}"},
        "workItemType": {"href": urls.work_item_type(kind)},
        "fields": {"href": f"{urls.wit}/fields"},
    }


def work_item(
    view: ItemView,
    urls: Urls,
    *,
    only: list[str] | None = None,
    relations: bool = False,
    links: bool = False,
    revision_url: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": view.id,
        "rev": view.rev,
        "fields": fields(view.fields, urls, only),
    }
    if relations and view.relations:
        body["relations"] = [relation(r, urls) for r in view.relations]
    if links:
        body["_links"] = work_item_links(view.id, str(view.fields.get("System.WorkItemType")), urls)
    body["url"] = (
        f"{urls.item(view.id)}/revisions/{view.rev}" if revision_url else urls.item(view.id)
    )
    return body


def update(item: UpdateView, urls: Urls) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": item.id,
        "workItemId": item.work_item_id,
        "rev": item.rev,
        "revisedBy": identity_ref(item.revised_by, urls, with_name=True),
        "revisedDate": item.revised_date,
    }
    if item.fields:
        body["fields"] = {
            ref: {key: _value(value, urls) for key, value in change.items()}
            for ref, change in item.fields.items()
        }
    if item.relations:
        body["relations"] = {
            kind: [_stored_relation(r, urls) for r in entries]
            for kind, entries in item.relations.items()
        }
    body["url"] = f"{urls.item(item.work_item_id)}/updates/{item.id}"
    return body


def collection(values: list[Any]) -> dict[str, Any]:
    return {"count": len(values), "value": values}
