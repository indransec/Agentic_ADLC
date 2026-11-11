"""The web application's only way to the platform: the API (007 FR-020, research R-01).

The bearer token lives in the Streamlit session state on the server, never in the browser.
Tests inject a client whose HTTP client is FastAPI's test client over the real app.
"""

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, kind: str, detail: str, field_name: str | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.kind = kind
        self.detail = detail
        self.field = field_name

    @property
    def signed_out(self) -> bool:
        return self.status == 401


@dataclass
class ApiClient:
    http: httpx.Client
    token: str | None = None
    person: Mapping[str, Any] | None = field(default=None)

    @classmethod
    def for_url(cls, base_url: str) -> "ApiClient":
        return cls(httpx.Client(base_url=base_url, timeout=30.0))

    def _headers(self) -> dict[str, str]:
        return {} if self.token is None else {"Authorization": f"Bearer {self.token}"}

    def _check(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            try:
                data = response.json()
            except ValueError:
                data = {}
            kind = (
                "not_signed_in" if response.status_code == 401 else str(data.get("kind", "error"))
            )
            raise ApiError(
                response.status_code,
                kind,
                str(data.get("detail", "request failed")),
                data.get("field"),
            )
        if response.status_code == 204 or not response.content:
            return None
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.content

    def sign_in(self, account_name: str, password: str) -> Mapping[str, Any]:
        data = self._check(
            self.http.post(
                "/auth/sign-in", json={"account_name": account_name, "password": password}
            )
        )
        self.token, self.person = str(data["token"]), dict(data["person"])
        return self.person

    def sign_out(self) -> None:
        if self.token is not None:
            with contextlib.suppress(ApiError):  # signing out an expired session is fine
                self._check(self.http.post("/auth/sign-out", headers=self._headers()))
        self.token, self.person = None, None

    def get(self, path: str, **params: Any) -> Any:
        return self._check(self.http.get(path, headers=self._headers(), params=params or None))

    def post(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self._check(self.http.post(path, headers=self._headers(), json=dict(body or {})))

    def put(self, path: str, body: Mapping[str, Any]) -> Any:
        return self._check(self.http.put(path, headers=self._headers(), json=dict(body)))

    def upload(self, path: str, name: str, data: bytes, media_type: str, version: int) -> Any:
        return self._check(
            self.http.post(
                path,
                headers=self._headers(),
                files={"file": (name, data, media_type)},
                data={"expected_version": str(version)},
            )
        )
