"""ADO error bodies and status codes (research R-02).

Clients must rely on the status code; the message, ``typeName`` and ``typeKey`` texts are the
simulator's own (a listed difference from real ADO).
"""

from __future__ import annotations

from typing import Any

_TYPE_PREFIX = "Microsoft.TeamFoundation.WorkItemTracking.Server."


class AdoError(Exception):
    def __init__(self, status: int, message: str, type_key: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.type_key = type_key or _DEFAULT_TYPE_KEYS.get(status, "VssServiceException")

    def body(self) -> dict[str, Any]:
        return error_body(self.message, self.type_key)


_DEFAULT_TYPE_KEYS = {
    400: "VssPropertyValidationException",
    404: "WorkItemUnauthorizedAccessException",
    412: "WorkItemRevisionMismatchException",
}


def error_body(message: str, type_key: str) -> dict[str, Any]:
    return {
        "$id": "1",
        "innerException": None,
        "message": message,
        "typeName": f"{_TYPE_PREFIX}{type_key}, {_TYPE_PREFIX.rstrip('.')}",
        "typeKey": type_key,
        "errorCode": 0,
        "eventId": 3000,
    }


def invalid(message: str, type_key: str | None = None) -> AdoError:
    return AdoError(400, message, type_key)


def not_found(message: str, type_key: str | None = None) -> AdoError:
    return AdoError(404, message, type_key)


def conflict(message: str) -> AdoError:
    return AdoError(412, message)


def work_item_not_found(item_id: int) -> AdoError:
    return not_found(
        f"TF401232: Work item {item_id} does not exist, or you do not have permissions to read it."
    )
