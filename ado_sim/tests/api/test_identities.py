"""US6: identities and access (T035)."""

from pathlib import Path

from ado_sim import auth
from ado_sim.db import Database
from tests.conftest import KEY, LEAD, OWNER, WIT, ApiClient, title

IDENTITIES = "/adlc-demo/_apis/identities"


def test_requests_without_a_valid_token_are_refused_alike(api: ApiClient, db: Database) -> None:
    item_id = api.new("Task", "t")
    revoked_id, revoked = auth.issue(db, KEY, OWNER)
    auth.revoke(db, revoked_id)
    path = f"{WIT}/workitems/{item_id}"
    responses = [
        api.http.get(path, params={"api-version": "7.1"}),
        api.http.get(path, params={"api-version": "7.1"}, headers={"Authorization": "Bearer nope"}),
        api.http.get(path, params={"api-version": "7.1"}, headers={"Authorization": f"Bearer {revoked}"}),
        api.http.patch(
            path,
            params={"api-version": "7.1"},
            headers={"Authorization": "Basic Og==", "Content-Type": "application/json-patch+json"},
            content=b'[{"op": "add", "path": "/fields/System.Title", "value": "x"}]',
        ),
    ]
    assert {r.status_code for r in responses} == {401}
    assert {r.content for r in responses} == {b""}
    assert api.call("GET", path).json()["rev"] == 1


def test_changes_record_the_token_holder(api: ApiClient) -> None:
    item_id = api.new("Task", "t")
    response = api.patch(item_id, [title("by lead")], user=LEAD)
    assert response.json()["fields"]["System.ChangedBy"]["uniqueName"] == LEAD


def test_lookup_by_name_and_id(api: ApiClient) -> None:
    by_name = api.call(
        "GET", IDENTITIES, params={"searchFilter": "General", "filterValue": OWNER}
    ).json()
    assert by_name["count"] == 1
    person = by_name["value"][0]
    assert person["providerDisplayName"] == "Product Owner"
    assert person["properties"]["Account"]["$value"] == OWNER
    assert person["isActive"] is True
    by_display = api.call(
        "GET", IDENTITIES, params={"searchFilter": "General", "filterValue": "product owner"}
    ).json()
    assert by_display["value"][0]["id"] == person["id"]
    by_id = api.call(
        "GET", IDENTITIES, params={"identityIds": person["id"].replace("-", "")}
    ).json()
    assert [p["id"] for p in by_id["value"]] == [person["id"]]
    none = api.call("GET", IDENTITIES, params={"searchFilter": "General", "filterValue": "x@y"})
    assert none.json()["count"] == 0


def test_identity_refusals(api: ApiClient) -> None:
    assert api.call("GET", IDENTITIES).status_code == 400
    bad_filter = api.call("GET", IDENTITIES, params={"searchFilter": "Odd", "filterValue": "x"})
    assert bad_filter.status_code == 400
    assert api.call("GET", "/other-org/_apis/identities", params={"identityIds": "x"}).status_code == 404


def test_revoked_token_stops_working(api: ApiClient, db: Database, tmp_path: Path) -> None:
    token_id, token = auth.issue(db, KEY, LEAD)
    path = f"{WIT}/workitems"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"api-version": "7.1", "ids": "1", "errorPolicy": "Omit"}
    assert api.http.get(path, params=params, headers=headers).status_code == 200
    auth.revoke(db, token_id)
    assert api.http.get(path, params=params, headers=headers).status_code == 401
