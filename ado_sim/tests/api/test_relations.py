"""US4: links through the API (T031)."""

from typing import Any

from tests.conftest import OWNER, WIT, ApiClient

PARENT = "System.LinkTypes.Hierarchy-Reverse"
CHILD = "System.LinkTypes.Hierarchy-Forward"


def link(rel: str, target: int) -> dict[str, Any]:
    return {
        "op": "add",
        "path": "/relations/-",
        "value": {"rel": rel, "url": f"http://anything/_apis/wit/workItems/{target}"},
    }


def relations(api: ApiClient, item_id: int) -> list[tuple[str, str, str]]:
    body = api.call("GET", f"{WIT}/workitems/{item_id}", params={"$expand": "Relations"}).json()
    return [
        (r["rel"], r["url"].rsplit("/", 1)[-1], r["attributes"]["name"])
        for r in body.get("relations", [])
    ]


def test_parent_link_shows_on_both_and_revisions(api: ApiClient) -> None:
    epic = api.new("Epic", "e")
    task = api.new("Task", "t")
    response = api.patch(task, [link(PARENT, epic)], user=OWNER)
    assert response.status_code == 200
    assert response.json()["rev"] == 2
    assert relations(api, task) == [(PARENT, str(epic), "Parent")]
    assert relations(api, epic) == [(CHILD, str(task), "Child")]
    epic_updates = api.call("GET", f"{WIT}/workitems/{epic}/updates").json()["value"]
    assert epic_updates[-1]["relations"]["added"][0]["rel"] == CHILD
    assert epic_updates[-1]["rev"] == 1
    all_expand = api.call("GET", f"{WIT}/workitems/{task}", params={"$expand": "All"}).json()
    assert all_expand["relations"] and all_expand["_links"]
    plain = api.call("GET", f"{WIT}/workitems/{task}").json()
    assert "relations" not in plain


def test_second_parent_and_cycle_refused(api: ApiClient) -> None:
    a = api.new("Task", "a")
    b = api.new("Task", "b")
    c = api.new("Task", "c")
    other = api.new("Epic", "other")
    assert api.patch(b, [link(PARENT, a)]).status_code == 200
    assert api.patch(c, [link(PARENT, b)]).status_code == 200
    assert api.patch(b, [link(PARENT, other)]).status_code == 400
    assert api.patch(a, [link(PARENT, c)]).status_code == 400
    assert relations(api, a) == [(CHILD, str(b), "Child")]


def test_remove_link(api: ApiClient) -> None:
    epic = api.new("Epic", "e")
    task = api.new("Task", "t")
    api.patch(task, [link(PARENT, epic)])
    response = api.patch(task, [{"op": "remove", "path": "/relations/0"}])
    assert response.status_code == 200
    assert relations(api, task) == [] and relations(api, epic) == []
