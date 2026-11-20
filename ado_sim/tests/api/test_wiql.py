"""US3: WIQL through the API (T027)."""

from typing import Any

from tests.conftest import WIT, ApiClient, add

LINK = "System.LinkTypes.Hierarchy-Reverse"


def query(api: ApiClient, text: str, **params: object) -> Any:
    return api.call("POST", f"{WIT}/wiql", params=dict(params), body={"query": text})


def test_epics_in_a_state_under_an_area(api: ApiClient) -> None:
    target = api.new("Epic", "match", **{"System.AreaPath": "Agentic ADLC\\Use cases"})
    api.new("Epic", "elsewhere")
    api.new("Task", "task", **{"System.AreaPath": "Agentic ADLC\\Use cases"})
    response = query(
        api,
        "SELECT [System.Id], [System.Title] FROM workitems WHERE [System.WorkItemType] = 'Epic'"
        " AND [System.State] = 'T0 Intake & Qualification'"
        " AND [System.AreaPath] UNDER 'Agentic ADLC\\Use cases' ORDER BY [System.Id]",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["queryType"] == "flat" and body["queryResultType"] == "workItem"
    assert [w["id"] for w in body["workItems"]] == [target]
    assert [c["referenceName"] for c in body["columns"]] == ["System.Id", "System.Title"]
    assert body["sortColumns"] == [{"field": body["columns"][0], "descending": False}]
    assert body["workItems"][0]["url"].endswith(f"/workItems/{target}")


def test_microsecond_changed_since(api: ApiClient) -> None:
    a = api.new("Task", "a")
    seen = api.call("GET", f"{WIT}/workitems/{a}").json()["fields"]["System.ChangedDate"]
    response = query(
        api,
        f"SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '{seen}'",
        timePrecision="true",
    )
    assert [w["id"] for w in response.json()["workItems"]] == [a]
    without = query(
        api, f"SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '{seen}'"
    )
    assert without.status_code == 400


def test_top(api: ApiClient) -> None:
    for name in "abc":
        api.new("Task", name)
    text = "SELECT [System.Id] FROM workitems ORDER BY [System.Id] DESC"
    assert [w["id"] for w in query(api, text, **{"$top": 2}).json()["workItems"]] == [3, 2]
    assert query(api, text, **{"$top": 20001}).status_code == 400


def test_link_query_result_shape(api: ApiClient) -> None:
    epic = api.new("Epic", "e")
    child = api.create(
        "Task",
        [
            add("/fields/System.Title", "c"),
            add("/relations/-", {"rel": LINK, "url": f"http://x/_apis/wit/workItems/{epic}"}),
        ],
    ).json()["id"]
    body = query(
        api,
        f"SELECT [System.Id] FROM workitemLinks WHERE [Source].[System.Id] = {epic}"
        " AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward' MODE (MustContain)",
    ).json()
    assert body["queryType"] == "oneHop" and body["queryResultType"] == "workItemLink"
    pairs = [
        (r["rel"], r["source"] and r["source"]["id"], r["target"]["id"])
        for r in body["workItemRelations"]
    ]
    assert pairs == [(None, None, epic), ("System.LinkTypes.Hierarchy-Forward", epic, child)]


def test_unsupported_and_bad_bodies(api: ApiClient) -> None:
    response = query(api, "SELECT [System.Id] FROM workitems WHERE [System.State] EVER 'x'")
    assert response.status_code == 400
    assert "EVER" in response.json()["message"]
    assert api.call("POST", f"{WIT}/wiql", body={"q": "x"}).status_code == 400
    assert api.call("POST", f"{WIT}/wiql", body=["x"]).status_code == 400
