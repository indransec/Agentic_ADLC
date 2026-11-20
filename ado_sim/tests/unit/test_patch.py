"""ADO JSON Patch (T018, written before ado_sim.patch)."""

from typing import Any

import pytest

from ado_sim.errors import AdoError
from ado_sim.patch import MAX_OPERATIONS, Relation, apply_patch, relation_target
from ado_sim.process import SYSTEM_FIELDS, FieldDef, Identity, TypeInfo

FIELDS = {f.reference_name.lower(): f for f in SYSTEM_FIELDS}
FIELDS.update(
    {
        "custom.note": FieldDef("Custom.Note", "Note", "plainText", False),
        "custom.count": FieldDef("Custom.Count", "Count", "integer", False),
        "custom.score": FieldDef("Custom.Score", "Score", "double", False),
        "custom.flag": FieldDef("Custom.Flag", "Flag", "boolean", False),
        "custom.due": FieldDef("Custom.Due", "Due", "dateTime", False),
        "custom.choice": FieldDef("Custom.Choice", "Choice", "string", False, ("Go", "Stop")),
    }
)
KIND = TypeInfo(
    "Task",
    "Microsoft.VSTS.WorkItemTypes.Task",
    "",
    "F2CB1D",
    (("New", "Proposed", ""), ("Active", "InProgress", ""), ("Closed", "Completed", "")),
    FIELDS,
)
AREAS = {"proj": "Proj", "proj\\team": "Proj\\Team"}
ALICE = Identity("a-id", "Alice", "alice@x")


def resolve(name: str) -> Identity | None:
    return ALICE if name.lower() in {"alice@x", "alice", "alice <alice@x>"} else None


def run(
    operations: Any,
    fields: dict[str, Any] | None = None,
    relations: list[Relation] | None = None,
    rev: int | None = 3,
) -> Any:
    return apply_patch(
        operations,
        kind=KIND,
        fields=fields if fields is not None else {"System.Title": "t", "System.State": "New"},
        relations=relations or [],
        rev=rev,
        area_paths=AREAS,
        resolve_identity=resolve,
    )


def status_of(operations: Any, **kwargs: Any) -> int:
    with pytest.raises(AdoError) as raised:
        run(operations, **kwargs)
    return raised.value.status


def op(kind: str, path: str, value: Any = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"op": kind, "path": path}
    if kind != "remove":
        entry["value"] = value
    return entry


def test_add_replace_remove_fields() -> None:
    result = run(
        [
            op("add", "/fields/System.Title", "new"),
            op("replace", "/fields/custom.note", "a note"),
            op("add", "/fields/Custom.Count", 4),
            op("remove", "/fields/Custom.Score"),
        ],
        fields={"System.Title": "t", "System.State": "New", "Custom.Score": 2.0},
    )
    assert result.fields == {
        "System.Title": "new",
        "System.State": "New",
        "Custom.Note": "a note",
        "Custom.Count": 4,
    }
    assert result.changed


def test_values_are_converted_by_type() -> None:
    result = run(
        [
            op("add", "/fields/Custom.Count", "12"),
            op("add", "/fields/Custom.Score", 1),
            op("add", "/fields/Custom.Flag", "true"),
            op("add", "/fields/Custom.Due", "2026-11-20T10:00:00Z"),
            op("add", "/fields/System.AssignedTo", "Alice <alice@x>"),
            op("add", "/fields/System.AreaPath", "proj\\TEAM"),
            op("add", "/fields/System.State", "active"),
            op("add", "/fields/Custom.Choice", "go"),
        ]
    )
    assert result.fields["Custom.Count"] == 12
    assert result.fields["Custom.Score"] == 1.0
    assert result.fields["Custom.Flag"] is True
    assert result.fields["Custom.Due"] == "2026-11-20T10:00:00.000000Z"
    assert result.fields["System.AssignedTo"] == ALICE.reference()
    assert result.fields["System.AreaPath"] == "Proj\\Team"
    assert result.fields["System.State"] == "Active"
    assert result.fields["Custom.Choice"] == "Go"


def test_test_rev() -> None:
    assert not run([op("test", "/rev", 3)]).changed
    assert status_of([op("test", "/rev", 2), op("add", "/fields/System.Title", "x")]) == 412
    assert status_of([op("test", "/rev", 3)], rev=None) == 400
    assert status_of([op("add", "/rev", 3)]) == 400


def test_test_field() -> None:
    assert not run([op("test", "/fields/System.Title", "t")]).changed
    assert status_of([op("test", "/fields/System.Title", "other")]) == 412


@pytest.mark.parametrize(
    "operations",
    [
        [op("add", "/fields/Custom.Missing", "x")],
        [op("add", "/fields/System.State", "Gone")],
        [op("add", "/fields/System.ChangedBy", "alice@x")],
        [op("add", "/fields/System.History", "text")],
        [op("add", "/fields/Custom.Count", "many")],
        [op("add", "/fields/Custom.Count", True)],
        [op("add", "/fields/Custom.Flag", "maybe")],
        [op("add", "/fields/Custom.Due", "yesterday")],
        [op("add", "/fields/System.AssignedTo", "nobody@x")],
        [op("add", "/fields/System.AreaPath", "Other\\Area")],
        [op("add", "/fields/Custom.Choice", "Maybe")],
        [op("add", "/fields/System.Title", "x" * 256)],
        [op("remove", "/fields/System.State")],
        [op("replace", "/fields/System.Title", None)],
        [op("add", "/fields/Custom.Note", "x" * (1024 * 1024 + 1))],
        [op("copy", "/fields/System.Title", "x")],
        [op("add", "/nowhere", "x")],
        [{"path": "/fields/System.Title"}],
        [op("add", "/fields/System.Title", "ok"), op("add", "/fields/Custom.Missing", "x")],
        [],
        {"op": "add"},
        ["not an object"],
    ],
)
def test_invalid_patches_are_refused_whole(operations: Any) -> None:
    assert status_of(operations) == 400


def test_operation_limit() -> None:
    too_many = [op("add", "/fields/System.Title", str(i)) for i in range(MAX_OPERATIONS + 1)]
    assert status_of(too_many) == 400
    assert run(too_many[:MAX_OPERATIONS]).fields["System.Title"] == str(MAX_OPERATIONS - 1)


def test_no_effective_change() -> None:
    result = run([op("replace", "/fields/System.Title", "t")])
    assert not result.changed


def test_relations_parse() -> None:
    url = "http://host/org/proj/_apis/wit/workItems/42"
    result = run(
        [
            op(
                "add",
                "/relations/-",
                {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": url,
                    "attributes": {"comment": "c"},
                },
            )
        ]
    )
    assert result.added == [
        Relation("System.LinkTypes.Hierarchy-Reverse", 42, {"isLocked": False, "comment": "c"})
    ]
    assert result.relations == result.added
    assert result.changed


def test_relation_remove_by_index() -> None:
    existing = [
        Relation("System.LinkTypes.Dependency-Forward", 5, {"isLocked": False}),
        Relation("System.LinkTypes.Hierarchy-Reverse", 6, {"isLocked": False}),
    ]
    result = run([op("remove", "/relations/1")], relations=existing)
    assert result.removed == [existing[1]]
    assert result.relations == [existing[0]]
    assert status_of([op("remove", "/relations/5")], relations=existing) == 400


@pytest.mark.parametrize(
    "value",
    [
        {"rel": "System.LinkTypes.Related", "url": "http://h/_apis/wit/workItems/1"},
        {"rel": "System.LinkTypes.Hierarchy-Forward", "url": "http://h/elsewhere/1"},
        {"rel": "System.LinkTypes.Hierarchy-Forward"},
        "not a relation",
    ],
)
def test_bad_relations(value: Any) -> None:
    assert status_of([op("add", "/relations/-", value)]) == 400


def test_duplicate_relation() -> None:
    existing = [Relation("System.LinkTypes.Dependency-Forward", 5, {"isLocked": False})]
    value = {"rel": "System.LinkTypes.Dependency-Forward", "url": "http://h/_apis/wit/workItems/5"}
    assert status_of([op("add", "/relations/-", value)], relations=existing) == 400


def test_relation_target() -> None:
    assert relation_target("https://dev.azure.com/o/_apis/wit/workItems/9") == 9
    assert relation_target("http://h/o/p/_apis/wit/workitems/10") == 10
    assert relation_target("http://h/o/p/_apis/wit/workitems/x") is None
