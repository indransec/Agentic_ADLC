"""US7: process and area reads match the seed (T037); simulator-only routes."""

from ado_sim.seed import read_seed
from tests.conftest import SEED, WIT, ApiClient


def test_types_and_states_match_the_seed(api: ApiClient) -> None:
    seed = read_seed(SEED)
    body = api.call("GET", f"{WIT}/workitemtypes").json()
    assert [t["name"] for t in body["value"]] == [t.name for t in seed.types]
    epic = api.call("GET", f"{WIT}/workitemtypes/Epic").json()
    seeded_epic = next(t for t in seed.types if t.name == "Epic")
    assert [s["name"] for s in epic["states"]] == [s.name for s in seeded_epic.states]
    assert {f["referenceName"] for f in epic["fields"]} >= {"Custom.AdlcSubStage", "System.Title"}
    states = api.call("GET", f"{WIT}/workitemtypes/User%20Story/states").json()
    assert [(s["name"], s["category"]) for s in states["value"]][:2] == [
        ("New", "Proposed"),
        ("Active", "InProgress"),
    ]
    assert api.call("GET", f"{WIT}/workitemtypes/Nope").status_code == 404
    assert api.call("GET", f"{WIT}/workitemtypes/Nope/states").status_code == 404


def test_fields(api: ApiClient) -> None:
    body = api.call("GET", f"{WIT}/fields").json()
    by_name = {f["referenceName"]: f for f in body["value"]}
    assert by_name["Custom.AdlcDecision"]["type"] == "string"
    assert by_name["System.ChangedBy"]["isIdentity"] is True
    assert by_name["System.Id"]["readOnly"] is True


def test_area_tree(api: ApiClient) -> None:
    root = api.call("GET", f"{WIT}/classificationnodes/Areas").json()
    assert root["name"] == "Agentic ADLC" and root["hasChildren"] is True
    assert "children" not in root
    deep = api.call("GET", f"{WIT}/classificationnodes/Areas", params={"$depth": 2}).json()
    assert [c["name"] for c in deep["children"]] == ["Use cases"]
    assert deep["children"][0]["path"] == "\\Agentic ADLC\\Area\\Use cases"


def test_health_and_contract_need_no_token(api: ApiClient) -> None:
    assert api.http.get("/health").json() == {"status": "ok"}
    contract = api.http.get("/openapi.json")
    assert contract.status_code == 200 and contract.json()["info"]["title"] == "ADO simulator"


def test_api_version_rules(api: ApiClient) -> None:
    assert api.call("GET", f"{WIT}/fields", api_version=None).status_code == 400
    assert api.call("GET", f"{WIT}/fields", api_version="6.0").status_code == 400


def test_unknown_project_and_operation(api: ApiClient) -> None:
    assert api.call("GET", "/adlc-demo/Other/_apis/wit/fields").status_code == 404
    assert api.call("GET", "/other/Agentic%20ADLC/_apis/wit/fields").status_code == 404
    unsupported = api.call("GET", f"{WIT}/queries")
    assert unsupported.status_code == 404 and unsupported.json()["message"]
    assert api.call("DELETE", f"{WIT}/workitems/1").status_code == 404


def test_body_limit(api: ApiClient) -> None:
    big = b"[" + b" " * (5 * 1024 * 1024 + 1) + b"]"
    response = api.http.post(
        f"{WIT}/workitemsbatch",
        params={"api-version": "7.1"},
        headers={**api.headers("adlc-platform@adlc.demo", "application/json")},
        content=big,
    )
    assert response.status_code == 400
