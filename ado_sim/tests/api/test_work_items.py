"""US1: create, read and update work items through the API (T019)."""

from typing import Any

from tests.conftest import LEAD, OWNER, SERVICE, WIT, ApiClient, add, title

EPIC_STAGE_1 = "T0 Intake & Qualification"
EPIC_STAGE_2 = "T1 Requirements & Outcome"


def test_create_returns_system_fields(api: ApiClient) -> None:
    response = api.create(
        "Epic",
        [
            title("Use case"),
            add("/fields/System.AreaPath", "Agentic ADLC\\Use cases"),
            add("/fields/Custom.AdlcUseCaseId", "UC-1"),
        ],
    )
    assert response.status_code == 200
    item = response.json()
    fields = item["fields"]
    assert item["id"] == 1 and item["rev"] == 1
    assert fields["System.Title"] == "Use case"
    assert fields["Custom.AdlcUseCaseId"] == "UC-1"
    assert fields["System.State"] == EPIC_STAGE_1
    assert fields["System.WorkItemType"] == "Epic"
    assert fields["System.TeamProject"] == "Agentic ADLC"
    assert fields["System.CreatedBy"]["uniqueName"] == SERVICE
    assert fields["System.ChangedBy"]["uniqueName"] == SERVICE
    assert fields["System.CreatedDate"] == fields["System.ChangedDate"]
    assert item["url"].endswith("/_apis/wit/workItems/1")
    assert set(item["_links"]) >= {"self", "workItemUpdates", "workItemRevisions", "html"}


def test_default_area_is_the_project_root(api: ApiClient) -> None:
    item = api.create("Task", [title("t")]).json()
    assert item["fields"]["System.AreaPath"] == "Agentic ADLC"
    assert item["fields"]["System.State"] == "New"


def test_update_with_rev_test(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    for value in ("a", "b"):
        assert api.patch(item_id, [title(value)]).status_code == 200
    response = api.patch(
        item_id,
        [
            {"op": "test", "path": "/rev", "value": 3},
            add("/fields/System.Title", "four"),
            add("/fields/System.State", "Active"),
        ],
        user=OWNER,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rev"] == 4
    assert body["fields"]["System.Title"] == "four"
    assert body["fields"]["System.State"] == "Active"
    assert body["fields"]["System.ChangedBy"]["uniqueName"] == OWNER


def test_stale_rev_is_refused_and_nothing_changes(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    api.patch(item_id, [title("second")])
    response = api.patch(
        item_id, [{"op": "test", "path": "/rev", "value": 1}, title("lost")], user=LEAD
    )
    assert response.status_code == 412
    assert set(response.json()) >= {"message", "typeKey", "$id"}
    item = api.call("GET", f"{WIT}/workitems/{item_id}").json()
    assert item["rev"] == 2 and item["fields"]["System.Title"] == "second"


def test_list_in_order_with_fields(api: ApiClient) -> None:
    ids = [api.new("Task", f"t{i}") for i in range(10)]
    wanted = [ids[7], ids[2], ids[5], ids[0], ids[9], ids[1], ids[4], ids[3]]
    response = api.call(
        "GET",
        f"{WIT}/workitems",
        params={"ids": ",".join(map(str, wanted)), "fields": "System.Id,System.Title"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 8
    assert [v["id"] for v in body["value"]] == wanted
    assert all(set(v["fields"]) == {"System.Id", "System.Title"} for v in body["value"])


def test_batch(api: ApiClient) -> None:
    ids = [api.new("Task", f"t{i}") for i in range(3)]
    response = api.call(
        "POST",
        f"{WIT}/workitemsbatch",
        body={"ids": [ids[2], ids[0]], "fields": ["System.Title"]},
    )
    assert response.status_code == 200
    assert [v["fields"] for v in response.json()["value"]] == [
        {"System.Title": "t2"},
        {"System.Title": "t0"},
    ]


def test_error_policy_and_id_limit(api: ApiClient) -> None:
    item_id = api.new()
    missing = {"ids": f"{item_id},999"}
    assert api.call("GET", f"{WIT}/workitems", params=missing).status_code == 404
    omitted = api.call("GET", f"{WIT}/workitems", params={**missing, "errorPolicy": "Omit"})
    assert [v["id"] for v in omitted.json()["value"]] == [item_id]
    batch = api.call(
        "POST", f"{WIT}/workitemsbatch", body={"ids": [item_id, 999], "errorPolicy": "omit"}
    )
    assert batch.json()["count"] == 1
    too_many = ",".join(str(i) for i in range(1, 202))
    assert api.call("GET", f"{WIT}/workitems", params={"ids": too_many}).status_code == 400
    assert (
        api.call("POST", f"{WIT}/workitemsbatch", body={"ids": list(range(1, 202))}).status_code
        == 400
    )


def test_unknown_field_or_state_is_refused(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    for operations in (
        [add("/fields/Custom.Nope", "x")],
        [add("/fields/System.State", EPIC_STAGE_2)],
        [title("ok"), add("/fields/System.State", "Nowhere")],
    ):
        response = api.patch(item_id, operations)
        assert response.status_code == 400
        assert response.json()["message"]
    item = api.call("GET", f"{WIT}/workitems/{item_id}").json()
    assert item["rev"] == 1 and item["fields"]["System.Title"] == "t"


def test_epic_moves_to_the_next_stage(api: ApiClient) -> None:
    epic = api.new("Epic", "use case")
    response = api.patch(
        epic,
        [
            add("/fields/System.State", EPIC_STAGE_2),
            add("/fields/Custom.AdlcSubStage", "drafting"),
        ],
        user=OWNER,
    )
    body = response.json()
    assert body["rev"] == 2
    assert body["fields"]["System.State"] == EPIC_STAGE_2
    assert body["fields"]["Custom.AdlcSubStage"] == "drafting"


def test_get_options(api: ApiClient) -> None:
    item_id = api.new("Task", "first")
    first_date = api.call("GET", f"{WIT}/workitems/{item_id}").json()["fields"][
        "System.ChangedDate"
    ]
    api.patch(item_id, [title("second")])
    as_of = api.call("GET", f"{WIT}/workitems/{item_id}", params={"asOf": first_date}).json()
    assert as_of["fields"]["System.Title"] == "first"
    only = api.call("GET", f"{WIT}/workitems/{item_id}", params={"fields": "System.Title"}).json()
    assert only["fields"] == {"System.Title": "second"} and "_links" not in only
    both = api.call(
        "GET",
        f"{WIT}/workitems/{item_id}",
        params={"fields": "System.Title", "$expand": "Relations"},
    )
    assert both.status_code == 400
    assert (
        api.call("GET", f"{WIT}/workitems/{item_id}", params={"fields": "Nope.Field"}).status_code
        == 400
    )
    assert (
        api.call("GET", f"{WIT}/workitems/{item_id}", params={"$expand": "Everything"}).status_code
        == 400
    )
    assert api.call("GET", f"{WIT}/workitems/{item_id}", params={"asOf": "soon"}).status_code == 400
    early = api.call(
        "GET", f"{WIT}/workitems/{item_id}", params={"asOf": "2000-01-01T00:00:00Z"}
    )
    assert early.status_code == 404


def test_validate_only_saves_nothing(api: ApiClient) -> None:
    preview = api.call(
        "POST",
        f"{WIT}/workitems/$Task",
        params={"validateOnly": "true"},
        body=[title("preview")],
        content_type="application/json-patch+json",
    )
    assert preview.status_code == 200
    assert preview.json()["fields"]["System.Title"] == "preview"
    item_id = api.new("Task", "real")
    assert item_id == 1
    checked = api.patch(item_id, [title("maybe")], validateOnly="true")
    assert checked.json()["fields"]["System.Title"] == "maybe"
    assert api.call("GET", f"{WIT}/workitems/{item_id}").json()["rev"] == 1


def test_refusals(api: ApiClient) -> None:
    assert api.create("Nonsense", [title("x")]).status_code == 404
    assert api.create("Task", [add("/fields/System.Description", "no title")]).status_code == 400
    assert api.call("GET", f"{WIT}/workitems/999").status_code == 404
    assert api.call("GET", f"{WIT}/workitems/abc").status_code == 400
    item_id = api.new()
    assert api.patch(item_id, [title("x")], bypassRules="true").status_code == 400
    wrong_type = api.call("PATCH", f"{WIT}/workitems/{item_id}", body=[title("x")])
    assert wrong_type.status_code == 415
    big = "x" * (1024 * 1024 + 10)
    assert api.patch(item_id, [add("/fields/Custom.AdlcComment", big)]).status_code == 400
    raw = api.http.request(
        "PATCH",
        f"{WIT}/workitems/{item_id}",
        params={"api-version": "7.1"},
        headers={**api.headers(SERVICE, "application/json-patch+json")},
        content=b"not json",
    )
    assert raw.status_code == 400


def test_paths_ignore_case(api: ApiClient) -> None:
    item_id = api.new()
    response = api.call("GET", f"/adlc-demo/Agentic%20ADLC/_apis/WIT/WorkItems/{item_id}")
    assert response.status_code == 200


def test_identity_fields(api: ApiClient) -> None:
    item_id = api.new("Bug", "b", **{"System.AssignedTo": "Engineering Lead"})
    assigned: dict[str, Any] = api.call("GET", f"{WIT}/workitems/{item_id}").json()["fields"][
        "System.AssignedTo"
    ]
    assert assigned["uniqueName"] == LEAD
    assert assigned["displayName"] == "Engineering Lead"
    assert assigned["url"].endswith(f"/_apis/identities/{assigned['id']}")
