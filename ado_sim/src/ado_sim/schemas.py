"""Response and request shapes for the published contract (``contract/openapi.json``).

These models document the API; handlers build plain JSON with ``ado_sim.render``. Extra keys are
allowed because ADO adds fields over time and clients must tolerate them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Link(_Open):
    href: str


class IdentityRef(_Open):
    displayName: str  # noqa: N815 - ADO's names
    url: str
    id: str
    uniqueName: str  # noqa: N815
    imageUrl: str | None = None  # noqa: N815
    descriptor: str | None = None


class Relation(_Open):
    rel: str
    url: str
    attributes: dict[str, Any]


class WorkItem(_Open):
    id: int
    rev: int
    fields: dict[str, Any]
    relations: list[Relation] | None = None
    links: dict[str, Link] | None = Field(default=None, alias="_links")
    url: str


class WorkItemList(_Open):
    count: int
    value: list[WorkItem]


class FieldChange(_Open):
    oldValue: Any = None  # noqa: N815
    newValue: Any = None  # noqa: N815


class RelationChanges(_Open):
    added: list[Relation] | None = None
    removed: list[Relation] | None = None
    updated: list[Relation] | None = None


class WorkItemUpdate(_Open):
    id: int
    workItemId: int  # noqa: N815
    rev: int
    revisedBy: IdentityRef  # noqa: N815
    revisedDate: str  # noqa: N815
    fields: dict[str, FieldChange] | None = None
    relations: RelationChanges | None = None
    url: str


class WorkItemUpdateList(_Open):
    count: int
    value: list[WorkItemUpdate]


class FieldReference(_Open):
    referenceName: str  # noqa: N815
    name: str
    url: str


class SortColumn(_Open):
    field: FieldReference
    descending: bool


class WorkItemReference(_Open):
    id: int
    url: str


class WorkItemLink(_Open):
    rel: str | None
    source: WorkItemReference | None
    target: WorkItemReference


class QueryResult(_Open):
    queryType: str  # noqa: N815
    queryResultType: str  # noqa: N815
    asOf: str  # noqa: N815
    columns: list[FieldReference]
    sortColumns: list[SortColumn]  # noqa: N815
    workItems: list[WorkItemReference] | None = None  # noqa: N815
    workItemRelations: list[WorkItemLink] | None = None  # noqa: N815


class Comment(_Open):
    workItemId: int  # noqa: N815
    id: int
    version: int
    text: str
    createdBy: IdentityRef  # noqa: N815
    createdDate: str  # noqa: N815
    modifiedBy: IdentityRef  # noqa: N815
    modifiedDate: str  # noqa: N815
    isDeleted: bool  # noqa: N815
    url: str


class CommentList(_Open):
    totalCount: int  # noqa: N815
    count: int
    comments: list[Comment]
    nextPage: str | None = None  # noqa: N815
    continuationToken: str | None = None  # noqa: N815


class State(_Open):
    name: str
    color: str
    category: str


class StateList(_Open):
    count: int
    value: list[State]


class TypeField(_Open):
    referenceName: str  # noqa: N815
    name: str
    alwaysRequired: bool  # noqa: N815
    url: str


class WorkItemType(_Open):
    name: str
    referenceName: str  # noqa: N815
    description: str
    color: str
    isDisabled: bool  # noqa: N815
    states: list[State]
    fields: list[TypeField]
    url: str


class WorkItemTypeList(_Open):
    count: int
    value: list[WorkItemType]


class WorkItemField(_Open):
    name: str
    referenceName: str  # noqa: N815
    type: str
    readOnly: bool  # noqa: N815
    usage: str
    isIdentity: bool  # noqa: N815
    url: str


class WorkItemFieldList(_Open):
    count: int
    value: list[WorkItemField]


class ClassificationNode(_Open):
    id: int
    identifier: str
    name: str
    structureType: str  # noqa: N815
    hasChildren: bool  # noqa: N815
    path: str
    children: list[ClassificationNode] | None = None
    url: str


class Identity(_Open):
    id: str
    descriptor: str
    providerDisplayName: str  # noqa: N815
    isActive: bool  # noqa: N815
    isContainer: bool  # noqa: N815
    properties: dict[str, Any]


class IdentityList(_Open):
    count: int
    value: list[Identity]


class Health(_Open):
    status: str


class AdoError(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="$id")
    innerException: Any = None  # noqa: N815
    message: str
    typeName: str  # noqa: N815
    typeKey: str  # noqa: N815
    errorCode: int  # noqa: N815
    eventId: int  # noqa: N815


ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": AdoError, "description": "Invalid request, refused whole"},
    401: {"description": "No valid personal access token (empty body)"},
    404: {"model": AdoError, "description": "Unknown organisation, project or resource"},
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    412: {"model": AdoError, "description": "A `test` operation failed (stale revision)"},
    415: {"model": AdoError, "description": "Content-Type is not application/json-patch+json"},
}

PATCH_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json-patch+json": {
                "schema": {
                    "type": "array",
                    "maxItems": 500,
                    "items": {
                        "type": "object",
                        "required": ["op", "path"],
                        "properties": {
                            "op": {"type": "string", "enum": ["add", "replace", "remove", "test"]},
                            "path": {"type": "string"},
                            "value": {},
                        },
                    },
                }
            }
        },
    }
}


def json_body(schema: dict[str, Any]) -> dict[str, Any]:
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}


BATCH_BODY = json_body(
    {
        "type": "object",
        "required": ["ids"],
        "properties": {
            "ids": {"type": "array", "items": {"type": "integer"}, "maxItems": 200},
            "fields": {"type": "array", "items": {"type": "string"}},
            "asOf": {"type": "string", "format": "date-time"},
            "$expand": {"type": "string", "enum": ["None", "Relations", "Fields", "Links", "All"]},
            "errorPolicy": {"type": "string", "enum": ["Fail", "Omit"]},
        },
    }
)
WIQL_BODY = json_body(
    {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string", "maxLength": 32768}},
    }
)
COMMENT_BODY = json_body(
    {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}
)
