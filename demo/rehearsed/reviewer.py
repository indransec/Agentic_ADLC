"""Rehearsed replies of the common terminal reviewer (feature 014): it reads the checklist it is
given and the failed controls, and recommends pass with every item scored, noting any failed
control as a finding. People decide; the demo's human steps differ from it where the script
says so (with a reason)."""

import json
from typing import Any

from demo.rehearsed.common import Messages


def _block(messages: Messages, source: str) -> list[Any]:
    marker = f'<data source="{source}">'
    for message in messages:
        content = message["content"]
        if marker in content:
            body = content[content.index(marker) + len(marker) :]
            found = json.loads(body[: body.index("</data>")])
            return found if isinstance(found, list) else []
    return []


def review(messages: Messages) -> str:
    checklist = _block(messages, "checklist")
    items = [str(i["id"]) for i in checklist if isinstance(i, dict) and "id" in i]
    controls = _block(messages, "control_results")
    failed = [
        c for c in controls if isinstance(c, dict) and c.get("blocking") and not c.get("passed")
    ]
    findings = [{"item": None, "text": f"{c['id']} failed: {c.get('reason', '')}"} for c in failed]
    return json.dumps(
        {
            "scores": dict.fromkeys(items, 3),
            "findings": findings,
            "recommendation": {
                "status": "pass",
                "reason": "The artifacts address every checklist item"
                + ("; the failed controls are for the approvers to decide." if failed else "."),
                "root_cause": None,
            },
        }
    )
