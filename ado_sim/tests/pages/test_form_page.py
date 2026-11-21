"""018: the work item form (US1, US2, US4, US5; FR-001 to FR-008, FR-011 to FR-013)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

import ado_sim.pages
from ado_sim.comments import add_comment
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages import a11y
from tests.pages.conftest import BOARD, ITEM, csrf_of, sign_in

PARENT = "System.LinkTypes.Hierarchy-Reverse"
DECISIONS = [
    "Pass",
    "Rework",
    "Exception",
    "Terminate",
    "Approve waiver",
    "Reject waiver",
    "Complete escalation",
]


def _parent(target: int) -> dict[str, object]:
    return add("/relations/-", {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{target}"})


def _run(store: WorkItemStore, people: People) -> tuple[int, int]:
    epic = store.create("Epic", [title("Claims triage")], people.service).id
    run = store.create(
        "Feature",
        [
            title("T1 run"),
            add(
                "/fields/System.Description",
                "<p>Decide: <b>Pass</b> or Rework</p><script>x()</script>",
            ),
            add("/fields/Custom.AdlcEvidenceLink", "https://console.test/runs/7"),
            _parent(epic),
        ],
        people.service,
    ).id
    return epic, run


def _fields(page: str) -> dict[str, str]:
    """The form's inputs with their current values (selects: the selected option)."""
    found: dict[str, str] = {}
    for name, value in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page):
        found[name] = value
    for name, body in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        chosen = re.search(r'<option value="([^"]*)" selected', body)
        found[name] = chosen.group(1) if chosen else ""
    for name, body in re.findall(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', page, re.S):
        found[name] = body
    return found


def _save(client: TestClient, item: int, page: str, **changes: str) -> httpx.Response:
    data = _fields(page)
    data.update({k.replace("__", "."): v for k, v in changes.items()})
    answer: httpx.Response = client.post(f"{ITEM}{item}", data=data)
    return answer


# ------------------------------------------------------------------------------ US1


def test_the_form_shows_sections_inputs_and_relations(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic, run = _run(store, people)
    sign_in(client)
    page = client.get(f"{ITEM}{run}")
    assert page.status_code == 200
    text = page.text
    assert "<legend>Decision</legend>" in text and "<legend>Run</legend>" in text
    options = re.search(r'name="Custom.AdlcDecision"[^>]*>(.*?)</select>', text, re.S)
    assert options is not None
    assert re.findall(r'<option value="([^"]+)"', options.group(1)) == DECISIONS
    assert "<b>Pass</b>" in text and "x()" not in text  # formatted, cleaned
    assert f'href="{ITEM}{epic}"' in text  # the parent
    assert 'name="rev" value="1"' in text
    assert a11y.problems(text) == []
    assert f'href="{BOARD}"' in text and "_backlogs/backlog" in text  # navigation


def test_a_save_is_the_person_s_one_update_of_changed_fields(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    _, run = _run(store, people)
    sign_in(client)
    page = client.get(f"{ITEM}{run}").text
    answer = _save(
        client, run, page, Custom__AdlcDecision="Pass", Custom__AdlcComment="Looks right"
    )
    assert answer.status_code == 303 and answer.headers["location"].endswith(f"/edit/{run}")
    updates = store.updates(run)
    assert len(updates) == 2
    last = updates[-1]
    assert last.revised_by["uniqueName"] == "product.owner@adlc.demo"
    changed = set(last.fields) - {"System.Rev", "System.ChangedDate", "System.ChangedBy"}
    assert changed == {"Custom.AdlcDecision", "Custom.AdlcComment"}
    # the description, edited as text, was not rewritten
    assert store.get(run).fields["System.Description"].startswith("<p>Decide")


def test_saving_nothing_changes_nothing(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    _, run = _run(store, people)
    sign_in(client)
    answer = _save(client, run, client.get(f"{ITEM}{run}").text)
    assert answer.status_code == 303
    assert store.get(run).rev == 1


def test_a_conflict_keeps_the_person_s_values_and_shows_the_current_item(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    _, run = _run(store, people)
    sign_in(client)
    page = client.get(f"{ITEM}{run}").text
    store.update(run, [add("/fields/System.Title", "Renamed by the platform")], people.service)
    answer = _save(client, run, page, Custom__AdlcDecision="Rework", Custom__AdlcReason="Gaps")
    assert answer.status_code == 412
    text = answer.text
    assert 'role="alert"' in text and "changed since" in text
    assert "Renamed by the platform" in text  # the current item
    shown = _fields(text)
    assert shown["Custom.AdlcDecision"] == "Rework" and shown["Custom.AdlcReason"] == "Gaps"
    assert shown["rev"] == "2"
    assert a11y.problems(text) == []
    again = client.post(f"{ITEM}{run}", data=shown)  # saving again succeeds, title kept
    assert again.status_code == 303
    fields = store.get(run).fields
    assert fields["System.Title"] == "Renamed by the platform"
    assert fields["Custom.AdlcDecision"] == "Rework"


def test_a_refusal_is_shown_beside_its_field(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    _, run = _run(store, people)
    sign_in(client)
    page = client.get(f"{ITEM}{run}").text
    answer = _save(client, run, page, System__Title="", Custom__AdlcComment="kept")
    assert answer.status_code == 400
    text = answer.text
    assert re.search(
        r'id="err-System.Title"[^>]*role="alert"|role="alert"[^>]*id="err-System.Title"', text
    )
    assert 'aria-describedby="err-System.Title"' in text
    assert _fields(text)["Custom.AdlcComment"] == "kept"
    assert a11y.problems(text) == []


def test_csrf_is_required(client: TestClient, store: WorkItemStore, people: People) -> None:
    _, run = _run(store, people)
    sign_in(client)
    data = _fields(client.get(f"{ITEM}{run}").text)
    data["csrf"] = "wrong"
    assert client.post(f"{ITEM}{run}", data=data).status_code == 403


def test_values_are_escaped(client: TestClient, store: WorkItemStore, people: People) -> None:
    item = store.create(
        "Feature",
        [title('<img src=x onerror="a()">'), add("/fields/Custom.AdlcValues", "</textarea><b>x")],
        people.service,
    ).id
    sign_in(client)
    text = client.get(f"{ITEM}{item}").text
    assert "<img" not in text and "</textarea><b>" not in text


def test_safe_is_used_once_for_the_cleaned_html() -> None:
    uses = [
        path.name
        for path in (Path(ado_sim.pages.__file__).parent / "templates").glob("*.html")
        for _ in re.finditer(r"\|\s*safe", path.read_text())
    ]
    assert uses == ["form.html"]


def test_unknown_item(client: TestClient) -> None:
    sign_in(client)
    assert client.get(f"{ITEM}999").status_code == 404
    assert client.post(f"{ITEM}999", data={"csrf": "x", "rev": "1"}).status_code in (403, 404)


# ------------------------------------------------------------------------------ US2


def test_a_clarification_is_answered_in_its_field(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    task = store.create(
        "Task",
        [title("Clarify"), add("/fields/System.Description", "<ol><li>Which region?</li></ol>")],
        people.service,
    ).id
    sign_in(client, "engineering.lead@adlc.demo")
    page = client.get(f"{ITEM}{task}").text
    assert "<legend>Clarification</legend>" in page and "<li>Which region?</li>" in page
    assert re.search(r'<textarea[^>]*name="Custom.AdlcClarificationAnswer"', page)
    answer = _save(client, task, page, Custom__AdlcClarificationAnswer="1. EU\r\n2. Yes")
    assert answer.status_code == 303
    last = store.updates(task)[-1]
    assert last.revised_by["uniqueName"] == "engineering.lead@adlc.demo"
    assert last.fields["Custom.AdlcClarificationAnswer"]["newValue"] == "1. EU\n2. Yes"


# ------------------------------------------------------------------------------ US4


def test_comments_newest_first_as_text(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    _, run = _run(store, people)
    add_comment(store, run, "first <b>platform</b> reply", people.service)
    sign_in(client)
    page = client.get(f"{ITEM}{run}").text
    answer = client.post(f"{ITEM}{run}/comments", data={"csrf": csrf_of(page), "text": "my note"})
    assert answer.status_code == 303 and answer.headers["location"].endswith("#comments")
    text = client.get(f"{ITEM}{run}").text
    comments = text[text.index('id="comments"') :]
    assert comments.index("my note") < comments.index("first &lt;b&gt;platform&lt;/b&gt; reply")
    assert "ADLC Platform" in comments and "Product Owner" in comments
    empty = client.post(f"{ITEM}{run}/comments", data={"csrf": csrf_of(page), "text": " "})
    assert empty.status_code == 400 and 'role="alert"' in empty.text
    assert a11y.problems(empty.text) == []


def test_history_and_the_evidence_link(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic, run = _run(store, people)
    store.update(run, [add("/fields/Custom.AdlcValues", "v" * 300)], people.owner)
    sign_in(client)
    text = client.get(f"{ITEM}{run}").text
    history = text[text.index('id="history"') :]
    assert "ADLC Values" in history and "v" * 200 + "…" in history and "v" * 300 in history
    assert f"Linked parent {epic}" in history
    assert '<a href="https://console.test/runs/7" target="_blank" rel="noopener noreferrer"' in text


# ------------------------------------------------------------------------------ US5


def test_a_platform_owned_field_is_saved_as_the_person_s_change(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic, _ = _run(store, people)
    sign_in(client)
    page = client.get(f"{ITEM}{epic}").text
    assert 'name="System.Id"' not in page and 'name="System.CreatedBy"' not in page  # read only
    answer = _save(client, epic, page, System__State="T4 Evaluation")
    assert answer.status_code == 303
    last = store.updates(epic)[-1]
    assert last.fields["System.State"]["newValue"] == "T4 Evaluation"
    assert last.revised_by["uniqueName"] == "product.owner@adlc.demo"
