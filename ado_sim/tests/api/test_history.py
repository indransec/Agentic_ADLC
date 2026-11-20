"""US2: every change, in order, with who made it (T024)."""

from tests.conftest import LEAD, OWNER, SERVICE, WIT, ApiClient, add, title


def test_updates_in_order_with_changers(api: ApiClient) -> None:
    item_id = api.new("Task", "start")
    api.patch(item_id, [title("one")], user=OWNER)
    api.patch(item_id, [add("/fields/System.State", "Active")], user=LEAD)
    api.patch(item_id, [title("three")], user=OWNER)
    body = api.call("GET", f"{WIT}/workitems/{item_id}/updates").json()
    assert body["count"] == 4
    updates = body["value"]
    assert [u["rev"] for u in updates] == [1, 2, 3, 4]
    assert [u["revisedBy"]["uniqueName"] for u in updates] == [SERVICE, OWNER, LEAD, OWNER]
    assert updates[1]["fields"]["System.Title"] == {"oldValue": "start", "newValue": "one"}
    assert updates[2]["fields"]["System.State"] == {"oldValue": "New", "newValue": "Active"}
    assert "oldValue" not in updates[0]["fields"]["System.Title"]
    assert updates[-1]["revisedDate"] == "9999-01-01T00:00:00Z"
    assert updates[0]["url"].endswith(f"/workItems/{item_id}/updates/1")
    assert updates[1]["revisedBy"]["name"] == f"Product Owner <{OWNER}>"


def test_update_paging_and_single(api: ApiClient) -> None:
    item_id = api.new("Task", "a")
    for value in "bcd":
        api.patch(item_id, [title(value)])
    page = api.call(
        "GET", f"{WIT}/workitems/{item_id}/updates", params={"$top": 2, "$skip": 1}
    ).json()
    assert [u["id"] for u in page["value"]] == [2, 3]
    single = api.call("GET", f"{WIT}/workitems/{item_id}/updates/3").json()
    assert single["fields"]["System.Title"] == {"oldValue": "b", "newValue": "c"}
    assert api.call("GET", f"{WIT}/workitems/{item_id}/updates/99").status_code == 404
    bad = api.call("GET", f"{WIT}/workitems/{item_id}/updates", params={"$top": 0})
    assert bad.status_code == 400
    negative = api.call("GET", f"{WIT}/workitems/{item_id}/updates", params={"$skip": -1})
    assert negative.status_code == 400


def test_revisions(api: ApiClient) -> None:
    item_id = api.new("Task", "a")
    api.patch(item_id, [title("b")], user=OWNER)
    revisions = api.call("GET", f"{WIT}/workitems/{item_id}/revisions").json()
    assert [r["rev"] for r in revisions["value"]] == [1, 2]
    first = api.call("GET", f"{WIT}/workitems/{item_id}/revisions/1").json()
    assert first["fields"]["System.Title"] == "a"
    assert first["fields"]["System.ChangedBy"]["uniqueName"] == SERVICE
    assert first["url"].endswith(f"/workItems/{item_id}/revisions/1")
    assert api.call("GET", f"{WIT}/workitems/{item_id}/revisions/5").status_code == 404
    assert api.call("GET", f"{WIT}/workitems/77/revisions").status_code == 404


def test_service_account_changes_are_distinguishable(api: ApiClient) -> None:
    item_id = api.new("Task", "a")
    api.patch(item_id, [title("person")], user=OWNER)
    api.patch(item_id, [title("platform")], user=SERVICE)
    updates = api.call("GET", f"{WIT}/workitems/{item_id}/updates").json()["value"]
    people = [u for u in updates if u["revisedBy"]["uniqueName"] != SERVICE]
    assert [u["rev"] for u in people] == [2]


def test_changed_since_finds_every_changed_item(api: ApiClient) -> None:
    first = api.new("Task", "a")
    mark = api.call("GET", f"{WIT}/workitems/{first}").json()["fields"]["System.ChangedDate"]
    second = api.new("Task", "b")
    api.patch(first, [title("a2")], user=OWNER)
    api.patch(first, [title("a3")], user=LEAD)
    query = (
        "SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '"
        + mark
        + "' ORDER BY [System.ChangedDate] ASC"
    )
    found = api.call(
        "POST", f"{WIT}/wiql", params={"timePrecision": "true"}, body={"query": query}
    ).json()
    assert [w["id"] for w in found["workItems"]] == [second, first]
    updates = api.call("GET", f"{WIT}/workitems/{first}/updates").json()["value"]
    assert [u["fields"]["System.Title"]["newValue"] for u in updates] == ["a", "a2", "a3"]
