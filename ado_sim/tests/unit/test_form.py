"""018 T006: the work item form model (FR-002, FR-003, FR-004, FR-008; research R-02, R-06)."""

from __future__ import annotations

from typing import Any

from ado_sim.db import Database
from ado_sim.pages import form
from ado_sim.process import FormSection, TypeInfo, form_layout, type_info
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title

PEOPLE = (form.Choice("product.owner@adlc.demo", "Product Owner"),)
AREAS = ("Agentic ADLC", "Agentic ADLC\\Use cases")


def _kind(db: Database, name: str) -> tuple[TypeInfo, tuple[FormSection, ...]]:
    with db.read() as conn:
        kind = type_info(conn, name)
        layout = form_layout(conn).get(name, ())
    assert kind is not None
    return kind, layout


def _by_ref(sections: list[form.Section]) -> dict[str, form.FormField]:
    return {f.ref: f for s in sections for f in s.fields}


def test_sections_follow_the_layout_then_other_fields(db: Database) -> None:
    kind, layout = _kind(db, "Feature")
    sections = form.sections(kind, layout, {}, PEOPLE, AREAS)
    assert [s.title for s in sections] == ["Decision", "Run", "Other fields"]
    assert [f.ref for f in sections[0].fields][:2] == ["Custom.AdlcDecision", "Custom.AdlcComment"]
    shown = [f.ref for s in sections for f in s.fields]
    assert len(shown) == len(set(shown))
    assert "System.History" not in shown  # the history field is the comments, not a form field
    assert {"System.Id", "System.Rev", "System.AssignedTo"} <= set(shown)


def test_without_a_layout_one_section_holds_every_field(db: Database) -> None:
    kind, _ = _kind(db, "User Story")
    sections = form.sections(kind, (), {}, PEOPLE, AREAS)
    assert [s.title for s in sections] == ["Fields"]


def test_inputs_by_field_type(db: Database) -> None:
    kind, layout = _kind(db, "Feature")
    fields = _by_ref(form.sections(kind, layout, {}, PEOPLE, AREAS))
    decision = fields["Custom.AdlcDecision"]
    assert decision.kind == "select"
    assert [c.value for c in decision.choices] == [
        "",
        "Pass",
        "Rework",
        "Exception",
        "Terminate",
        "Approve waiver",
        "Reject waiver",
        "Complete escalation",
    ]
    assert fields["System.State"].kind == "select"
    assert "" not in [c.value for c in fields["System.State"].choices]  # a required field
    assert [c.value for c in fields["System.AreaPath"].choices] == list(AREAS)
    assert fields["System.AssignedTo"].kind == "identity"
    assert [c.value for c in fields["System.AssignedTo"].choices] == ["", "product.owner@adlc.demo"]
    assert fields["System.Title"].kind == "text"
    assert fields["System.Description"].kind == "textarea"
    assert fields["Custom.AdlcValues"].kind == "textarea"  # plain text
    for ref in ("System.Id", "System.Rev", "System.CreatedBy", "System.ChangedDate"):
        assert fields[ref].kind == "readonly"


def test_values_as_text(db: Database, store: WorkItemStore, people: People) -> None:
    item = store.create(
        "Feature",
        [
            title("Run T1"),
            add("/fields/System.Description", "<p>Choose <b>Pass</b></p><ul><li>a</li></ul>"),
            add("/fields/Custom.AdlcEvidenceLink", "https://console.test/runs/7"),
            add("/fields/System.AssignedTo", "product.owner@adlc.demo"),
        ],
        people.owner,
    )
    kind, layout = _kind(db, "Feature")
    fields = _by_ref(form.sections(kind, layout, item.fields, PEOPLE, AREAS))
    description = fields["System.Description"]
    assert description.value == "Choose Pass\na"
    assert description.formatted == "<p>Choose <b>Pass</b></p><ul><li>a</li></ul>"
    assert fields["Custom.AdlcEvidenceLink"].link == "https://console.test/runs/7"
    assert fields["System.Title"].link is None
    assert fields["System.AssignedTo"].value == "product.owner@adlc.demo"
    assert fields["System.CreatedBy"].value == "Product Owner"


def test_typed_values_and_errors_override(db: Database) -> None:
    kind, layout = _kind(db, "Feature")
    fields = _by_ref(
        form.sections(
            kind,
            layout,
            {"System.Title": "old"},
            PEOPLE,
            AREAS,
            typed={"System.Title": "mine"},
            errors={"System.Title": "too long"},
        )
    )
    assert fields["System.Title"].value == "mine"
    assert fields["System.Title"].error == "too long"


def test_a_value_outside_the_choices_is_kept(db: Database) -> None:
    kind, layout = _kind(db, "Feature")
    fields = _by_ref(form.sections(kind, layout, {"System.AreaPath": "Gone"}, PEOPLE, AREAS))
    assert "Gone" in [c.value for c in fields["System.AreaPath"].choices]


# ------------------------------------------------------------------------------ operations


def _submitted(kind: TypeInfo, values: dict[str, Any], **changes: str) -> dict[str, str]:
    base = {
        f.ref: f.value
        for s in form.sections(kind, (), values, PEOPLE, AREAS)
        for f in s.fields
        if f.kind != "readonly"
    }
    base.update({k.replace("__", "."): v for k, v in changes.items()})
    return base


def test_only_changed_fields_with_the_revision_first(db: Database) -> None:
    kind, _ = _kind(db, "Feature")
    values = {"System.Title": "Run", "System.State": "New", "Custom.AdlcComment": "old"}
    submitted = _submitted(kind, values, Custom__AdlcDecision="Pass", Custom__AdlcComment="")
    ops = form.operations(kind, values, submitted, rev=4)
    assert ops == [
        {"op": "test", "path": "/rev", "value": 4},
        {"op": "remove", "path": "/fields/Custom.AdlcComment"},
        {"op": "add", "path": "/fields/Custom.AdlcDecision", "value": "Pass"},
    ]


def test_nothing_changed_means_no_operations(db: Database) -> None:
    kind, _ = _kind(db, "Feature")
    values = {"System.Title": "Run", "System.Description": "<p>One</p><p>Two</p>"}
    submitted = _submitted(kind, values)
    submitted["System.Description"] = "One\r\nTwo"  # a browser's line ends
    assert form.operations(kind, values, submitted, rev=2) == []


def test_html_fields_are_saved_escaped_in_paragraphs(db: Database) -> None:
    kind, _ = _kind(db, "Feature")
    values = {"System.Title": "Run"}
    submitted = _submitted(kind, values, System__Description="a <b>\n\nnext")
    ops = form.operations(kind, values, submitted, rev=1)
    assert ops[1] == {
        "op": "add",
        "path": "/fields/System.Description",
        "value": "<p>a &lt;b&gt;</p><p>next</p>",
    }


def test_read_only_and_unknown_inputs_are_ignored(db: Database) -> None:
    kind, _ = _kind(db, "Feature")
    values = {"System.Title": "Run"}
    submitted = _submitted(kind, values)
    submitted.update({"System.Rev": "99", "System.CreatedBy": "x", "Custom.Nope": "y"})
    assert form.operations(kind, values, submitted, rev=1) == []


def test_the_field_a_refusal_names(db: Database) -> None:
    kind, _ = _kind(db, "Feature")
    message = "The value for Custom.AdlcDecision is invalid: allowed values are Pass."
    assert form.field_of(kind, message) == "Custom.AdlcDecision"
    assert form.field_of(kind, "Something else went wrong.") is None


# ------------------------------------------------------------------------------ history


def test_history_entries(db: Database, store: WorkItemStore, people: People) -> None:
    parent = store.create("Epic", [title("Use case")], people.owner)
    item = store.create("Feature", [title("Run")], people.service)
    store.update(
        item.id,
        [
            add("/fields/Custom.AdlcDecision", "Pass"),
            add("/fields/Custom.AdlcValues", "x" * 250),
            add(
                "/relations/-",
                {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"http://sim/_apis/wit/workItems/{parent.id}",
                },
            ),
        ],
        people.owner,
    )
    kind, _ = _kind(db, "Feature")
    entries = form.history(store.updates(item.id), kind, lambda target: f"title {target}")
    newest, first = entries[0], entries[-1]
    assert newest.who == "Product Owner" and first.who == "ADLC Platform"
    labels = {c.label: c for c in newest.changes}
    assert labels["ADLC Decision"].old == "" and labels["ADLC Decision"].new == "Pass"
    values = labels["ADLC Values"]
    assert values.new == "x" * 250 and values.new_short == "x" * 200 + "…"
    assert "Rev" not in labels and "Changed Date" not in labels and "Changed By" not in labels
    assert newest.links == [f"Linked parent {parent.id}: title {parent.id}"]
    assert newest.when
