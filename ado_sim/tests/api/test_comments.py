"""US5: comments (T033)."""

from typing import Any

from tests.conftest import LEAD, OWNER, WIT, ApiClient

PREVIEW = "7.1-preview.4"


def add_comment(api: ApiClient, item_id: int, text: str, user: str) -> Any:
    return api.call(
        "POST",
        f"{WIT}/workitems/{item_id}/comments",
        user=user,
        body={"text": text},
        api_version=PREVIEW,
    )


def test_add_and_list_in_both_orders(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    for text, user in (("first", OWNER), ("second", LEAD), ("third", OWNER)):
        response = add_comment(api, item_id, text, user)
        assert response.status_code == 200
    created = response.json()
    assert created["text"] == "third" and created["version"] == 1
    assert created["createdBy"]["uniqueName"] == OWNER
    assert created["url"].endswith(f"/workItems/{item_id}/comments/{created['id']}")
    newest = api.call(
        "GET", f"{WIT}/workitems/{item_id}/comments", api_version=PREVIEW
    ).json()
    assert newest["totalCount"] == 3 and newest["count"] == 3
    assert [c["text"] for c in newest["comments"]] == ["third", "second", "first"]
    oldest = api.call(
        "GET",
        f"{WIT}/workitems/{item_id}/comments",
        params={"order": "asc"},
        api_version=PREVIEW,
    ).json()
    assert [(c["text"], c["createdBy"]["uniqueName"]) for c in oldest["comments"]] == [
        ("first", OWNER),
        ("second", LEAD),
        ("third", OWNER),
    ]


def test_comment_creates_a_revision_with_history(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    add_comment(api, item_id, "why it changed", OWNER)
    item = api.call("GET", f"{WIT}/workitems/{item_id}").json()
    assert item["rev"] == 2
    assert item["fields"]["System.CommentCount"] == 1
    assert "System.History" not in item["fields"]
    update = api.call("GET", f"{WIT}/workitems/{item_id}/updates").json()["value"][-1]
    assert update["fields"]["System.History"] == {"newValue": "why it changed"}
    assert update["fields"]["System.CommentCount"] == {"oldValue": 0, "newValue": 1}
    assert update["revisedBy"]["uniqueName"] == OWNER
    revision = api.call("GET", f"{WIT}/workitems/{item_id}/revisions/2").json()
    assert revision["fields"]["System.History"] == "why it changed"


def test_paging(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    for index in range(5):
        add_comment(api, item_id, f"c{index}", OWNER)
    seen: list[str] = []
    params: dict[str, object] = {"$top": 2, "order": "asc"}
    while True:
        page = api.call(
            "GET", f"{WIT}/workitems/{item_id}/comments", params=params, api_version=PREVIEW
        ).json()
        seen.extend(c["text"] for c in page["comments"])
        if "continuationToken" not in page:
            break
        assert "nextPage" in page
        params = {"$top": 2, "order": "asc", "continuationToken": page["continuationToken"]}
    assert seen == [f"c{i}" for i in range(5)]


def test_refusals(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    assert add_comment(api, item_id, "", OWNER).status_code == 400
    big = "x" * (1024 * 1024 + 1)
    assert add_comment(api, item_id, big, OWNER).status_code == 400
    assert add_comment(api, 999, "x", OWNER).status_code == 404
    wrong_version = api.call(
        "POST", f"{WIT}/workitems/{item_id}/comments", body={"text": "x"}, api_version="7.1"
    )
    assert wrong_version.status_code == 400
    path = f"{WIT}/workitems/{item_id}/comments"
    for params in ({"$top": 201}, {"order": "sideways"}, {"continuationToken": "garbage!"}):
        assert api.call("GET", path, params=params, api_version=PREVIEW).status_code == 400
