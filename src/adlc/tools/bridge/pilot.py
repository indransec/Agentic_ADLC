"""HTTP client for the pilot's operations (feature 009 contracts/pilot-api.md and 010
contracts/pilot-additions.md). The bridge never imports pilot code; it speaks to the pilot hosts,
``pilot-lab`` and the traffic generator over the pilot network."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from adlc.tools.mcp_app import ToolFailure

DEFAULT_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class PilotUrls:
    dev: str
    test: str
    prodsim: str
    lab: str
    traffic: str

    def host(self, environment: str) -> str:
        urls = {"dev": self.dev, "test": self.test, "prod-sim": self.prodsim}
        if environment not in urls:
            raise ToolFailure(f"invalid arguments: unknown environment {environment}")
        return urls[environment]


def _detail(reply: httpx.Response) -> str:
    try:
        body = reply.json()
    except ValueError:
        return reply.text[:300]
    detail = body.get("detail") if isinstance(body, Mapping) else None
    return str(detail if detail is not None else body)[:300]


class Pilot:
    def __init__(self, urls: PilotUrls, client: httpx.Client | None = None) -> None:
        self.urls = urls
        self.client = client or httpx.Client(timeout=DEFAULT_TIMEOUT_S)

    def request(
        self,
        method: str,
        base: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        missing_ok: bool = False,
    ) -> Any:
        """The answer's JSON; pilot refusals become tool errors, an unreachable pilot
        ``unavailable``. ``missing_ok`` turns a 404 into ``None``."""
        try:
            reply = self.client.request(
                method, f"{base.rstrip('/')}{path}", json=json, params=params, timeout=timeout_s
            )
        except httpx.TimeoutException as exc:
            raise ToolFailure(f"timed out: the pilot did not answer {path}") from exc
        except httpx.HTTPError as exc:
            raise ToolFailure(f"unavailable: the pilot at {path} is not reachable") from exc
        if reply.status_code == 404 and missing_ok:
            return None
        if reply.status_code == 404:
            raise ToolFailure(f"not found: {_detail(reply)}")
        if reply.status_code in (405, 409, 422):
            raise ToolFailure(f"refused: {_detail(reply)}")
        if reply.status_code >= 400:
            raise ToolFailure(f"failed: the pilot answered {reply.status_code}")
        return None if reply.status_code == 204 or not reply.content else reply.json()
