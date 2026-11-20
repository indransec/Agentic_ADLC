from ado_sim.errors import AdoError, conflict, error_body, invalid, not_found, work_item_not_found


def test_body_shape() -> None:
    body = error_body("bad", "SomeException")
    assert set(body) == {
        "$id",
        "innerException",
        "message",
        "typeName",
        "typeKey",
        "errorCode",
        "eventId",
    }
    assert body["message"] == "bad"
    assert body["typeKey"] == "SomeException"
    assert body["innerException"] is None


def test_statuses_and_default_keys() -> None:
    assert invalid("x").status == 400
    assert not_found("x").status == 404
    assert conflict("x").status == 412
    assert conflict("x").body()["typeKey"] == "WorkItemRevisionMismatchException"
    assert AdoError(500, "x").type_key == "VssServiceException"
    error = work_item_not_found(7)
    assert error.status == 404 and "Work item 7 does not exist" in error.message
