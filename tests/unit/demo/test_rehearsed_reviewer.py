"""014: the rehearsed reviewer's answer passes the platform's own review parser."""

import json

from demo.rehearsed.reviewer import review

from adlc.agents.context import data_block
from adlc.agents.output import parse_review

CHECKLIST = [{"id": "CHK-T1-01", "text": "a"}, {"id": "CHK-T1-02", "text": "b"}]


def _messages(controls: list[dict[str, object]]) -> list[dict[str, str]]:
    body = "\n".join([data_block("checklist", CHECKLIST), data_block("control_results", controls)])
    return [{"role": "system", "content": "reviewer"}, {"role": "user", "content": body}]


def test_scores_every_item_and_recommends_pass() -> None:
    raw = review(_messages([]))
    parsed = parse_review(raw, ["CHK-T1-01", "CHK-T1-02"], ["requirement"])
    assert not parsed.problems, parsed.problems
    assert json.loads(raw)["recommendation"]["status"] == "pass"


def test_failed_blocking_controls_become_findings() -> None:
    controls = [{"id": "CTL-T5-05", "passed": False, "blocking": True, "reason": "kill switch"}]
    raw = review(_messages(controls))
    assert not parse_review(raw, ["CHK-T1-01", "CHK-T1-02"], []).problems
    assert json.loads(raw)["findings"][0]["text"].startswith("CTL-T5-05 failed")
