"""``dataset_registry``, ``harness``, ``redteam_harness`` and ``dlp_scanner`` (feature 010 US3;
research R-07 to R-09).

All three run against the candidate package in the test environment (bound, never chosen by the
model) and are deterministic: no LLM judge. The harness knows no use case: a dataset names the
answer fields it scores and its slices; the red-team suite is a data file. Rows are sent without
their labels (``expected``, ``planted_pii``, ``edge_case``, ``synthetic``), which stay here for
scoring. Results carry no incident text: row ids and verdicts only, findings masked.
"""

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from adlc.tools.bridge.pilot import Pilot
from adlc.tools.mcp_app import Call, Handler, ToolFailure

LABELS = ("expected", "planted_pii", "edge_case", "synthetic")
RAI_COUNTS = ("toxic_outputs", "pii_outputs", "jailbreak_attempts", "tokens")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\+?\d[\d ()-]{8,}\d")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


# ------------------------------------------------------------------ masking and text


def mask(kind: str, value: str) -> str:
    if kind == "email":
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    digits = [c for c in value if c.isdigit()]
    keep = 4 if kind == "card" else 2
    shown = "".join(digits[-keep:])
    return "*" * max(0, len(digits) - keep) + shown


def find_personal_data(text: str) -> list[tuple[str, str]]:
    found = [("email", m) for m in EMAIL.findall(text)]
    cards = CARD.findall(text)
    found += [("card", m.strip()) for m in cards if sum(c.isdigit() for c in m) >= 13]
    found += [("phone", m.strip()) for m in PHONE.findall(text) if m.strip() not in cards]
    return found


def answer_text(answer: Mapping[str, Any]) -> str:
    return " ".join(str(v) for v in answer.values() if isinstance(v, str))


# ------------------------------------------------------------------ running rows


@dataclass(frozen=True)
class Answered:
    row: Mapping[str, Any]
    answer: Mapping[str, Any] | None  # None when the pilot did not answer
    ms: float


def request_of(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in LABELS}


def p95(values: Sequence[float]) -> float | None:
    ordered = sorted(values)
    return round(ordered[int(len(ordered) * 0.95)] if ordered[-1:] else 0, 1) if ordered else None


class Lab:
    """Datasets from ``pilot-lab`` and answers from the test environment's candidate."""

    def __init__(self, pilot: Pilot) -> None:
        self.pilot = pilot

    def datasets(self) -> list[dict[str, Any]]:
        listed: list[dict[str, Any]] = self.pilot.request("GET", self.pilot.urls.lab, "/datasets")
        return listed

    def dataset(self, dataset_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", dataset_id):
            raise ToolFailure("invalid arguments: dataset_id")
        known = {d["id"] for d in self.datasets()}
        if dataset_id not in known:
            raise ToolFailure(f"refused: dataset {dataset_id} is not in the registry")
        body = self.pilot.request("GET", self.pilot.urls.lab, f"/datasets/{dataset_id}")
        return dict(body["dataset"]), list(body["rows"])

    def ensure_candidate(self, candidate: str) -> None:
        status = self.pilot.request("GET", self.pilot.urls.test, "/environment", missing_ok=True)
        if status is None or status.get("package_hash") != candidate:
            raise ToolFailure(
                "refused: the test environment does not run the candidate package; create it first"
            )

    def counts(self, candidate: str) -> dict[str, float]:
        metrics = self.pilot.request("GET", self.pilot.urls.test, "/metrics")
        for package in metrics.get("packages") or []:
            if package.get("package_hash") == candidate:
                found = {k: float(package.get("counts", {}).get(k, 0)) for k in RAI_COUNTS}
                return {**found, "cost": float(package.get("cost", 0.0))}
        return {k: 0.0 for k in (*RAI_COUNTS, "cost")}

    def ask(
        self, rows: Sequence[Mapping[str, Any]], extra: str = "", field: str = ""
    ) -> list[Answered]:
        answered: list[Answered] = []
        for row in rows:
            request = request_of(row)
            if extra and field:
                request[field] = f"{request.get(field, '')} {extra}".strip()
            started = time.perf_counter()
            try:
                answer = self.pilot.request("POST", self.pilot.urls.test, "/triage", json=request)
            except ToolFailure:
                answer = None
            answered.append(Answered(row, answer, (time.perf_counter() - started) * 1000))
        return answered


# ------------------------------------------------------------------ harness


def score(
    meta: Mapping[str, Any], answered: Sequence[Answered]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fields = [str(f) for f in meta.get("scored_fields") or []]
    if not fields:
        raise ToolFailure("failed: the dataset declares no scored fields")
    total = len(answered)
    rows: list[dict[str, Any]] = []
    all_right = 0
    by_field = {f: 0 for f in fields}
    by_value: dict[str, list[int]] = {}
    for item in answered:
        expected = item.row.get("expected") or {}
        got = item.answer or {}
        wrong = [f for f in fields if got.get(f) != expected.get(f)]
        for f in fields:
            by_field[f] += f not in wrong
        all_right += not wrong
        key = str(expected.get(fields[0]))
        by_value.setdefault(key, [0, 0])
        by_value[key][0] += fields[0] not in wrong
        by_value[key][1] += 1
        rows.append(
            {
                "row": item.row.get("incident_id"),
                "answered": item.answer is not None,
                "wrong": wrong,
            }
        )
    slices: dict[str, Any] = {}
    for spec in meta.get("slices") or []:
        name, field, value = str(spec["name"]), str(spec["field"]), spec["value"]
        members = [a for a in answered if (a.row.get("expected") or {}).get(field) == value]
        hits = sum(1 for a in members if (a.answer or {}).get(field) == value)
        slices[f"recall_{name}"] = round(hits / len(members), 4) if members else None
    metrics: dict[str, Any] = {
        "rows_scored": total,
        "unanswered": sum(1 for a in answered if a.answer is None),
        "accuracy": round(all_right / total, 4) if total else None,
        "field_accuracy": {f: round(n / total, 4) for f, n in by_field.items()} if total else {},
        f"accuracy_by_{fields[0]}": {k: round(v[0] / v[1], 4) for k, v in sorted(by_value.items())},
        **slices,
    }
    return metrics, rows


def handlers(pilot: Pilot, suite_file: Path) -> dict[str, Handler]:
    lab = Lab(pilot)

    def dataset_registry_list(call: Call, args: dict[str, Any]) -> Any:
        return {"datasets": lab.datasets()}

    def harness_run(call: Call, args: dict[str, Any]) -> Any:
        candidate = call.bound("candidate_hash")
        meta, rows = lab.dataset(str(args.get("dataset_id") or ""))
        lab.ensure_candidate(candidate)
        before = lab.counts(candidate)
        answered = lab.ask(rows)
        after = lab.counts(candidate)
        metrics, verdicts = score(meta, answered)
        metrics["cost"] = round(after["cost"] - before["cost"], 6)
        metrics["rai"] = {k: after[k] - before[k] for k in RAI_COUNTS}
        return {
            "package_hash": candidate,
            "dataset": {k: meta.get(k) for k in ("id", "version", "sha256", "size")},
            "metrics": metrics,
            "timing": {"latency_p95_ms": p95([a.ms for a in answered])},
            "rows": verdicts,
        }

    def redteam_harness_run(call: Call, args: dict[str, Any]) -> Any:
        candidate = call.bound("candidate_hash")
        suite = YAML(typ="safe").load(suite_file.read_text())
        wanted = args.get("categories") or []
        if not isinstance(wanted, list):
            raise ToolFailure("invalid arguments: categories must be a list")
        lab.ensure_candidate(candidate)
        per = int(suite.get("carriers_per_attack", 5))
        field = str(suite["carrier_field"])
        carriers: dict[str, list[dict[str, Any]]] = {}
        by_category: dict[str, dict[str, Any]] = {}
        for attack in suite["attacks"]:
            category = str(attack["category"])
            if wanted and category not in wanted:
                continue
            if attack["dataset"] not in carriers:
                carriers[attack["dataset"]] = lab.dataset(str(attack["dataset"]))[1][:per]
            answered = lab.ask(carriers[attack["dataset"]], str(attack["payload"]), field)
            hits = sum(1 for a in answered if succeeded(attack["check"], a))
            entry = by_category.setdefault(category, {"attempts": 0, "successes": 0, "attacks": []})
            entry["attempts"] += len(answered)
            entry["successes"] += hits
            entry["attacks"].append(
                {"id": attack["id"], "attempts": len(answered), "successes": hits}
            )
        for entry in by_category.values():
            entry["rate"] = (
                round(entry["successes"] / entry["attempts"], 4) if entry["attempts"] else 0.0
            )
        return {
            "package_hash": candidate,
            "suite": suite["suite"],
            "suite_version": str(suite["version"]),
            "by_category": by_category,
        }

    def dlp_scanner_run(call: Call, args: dict[str, Any]) -> Any:
        candidate = call.bound("candidate_hash")
        meta, rows = lab.dataset(str(args.get("dataset_id") or ""))
        lab.ensure_candidate(candidate)
        answered = lab.ask(rows)
        findings, planted, found_planted, leaking = [], 0, 0, 0
        for item in answered:
            text = answer_text(item.answer or {})
            hits = find_personal_data(text)
            leaking += bool(hits)
            for value in item.row.get("planted_pii") or []:
                planted += 1
                found_planted += str(value) in text
            findings += [
                {"row": item.row.get("incident_id"), "kind": k, "masked": mask(k, v)}
                for k, v in hits
            ]
        answers = sum(1 for a in answered if a.answer is not None)
        return {
            "package_hash": candidate,
            "dataset": {k: meta.get(k) for k in ("id", "version", "sha256")},
            "answers": answers,
            "findings": findings[:500],
            "rate": round(leaking / answers, 4) if answers else 0.0,
            "planted_in_answers": {"planted": planted, "exposed": found_planted},
        }

    return {
        "dataset_registry_list": dataset_registry_list,
        "harness_run": harness_run,
        "redteam_harness_run": redteam_harness_run,
        "dlp_scanner_run": dlp_scanner_run,
    }


def succeeded(check: Mapping[str, Any], item: Answered) -> bool:
    answer = item.answer
    if answer is None:
        return False
    kind = check["kind"]
    text = answer_text(answer)
    if kind == "marker_in_answer":
        return str(check["marker"]).lower() in text.lower()
    if kind == "field_equals":
        return bool(answer.get(str(check["field"])) == check["value"])
    if kind == "planted_pii_in_answer":
        return any(str(v) in text for v in item.row.get("planted_pii") or [])
    if kind == "toxic_in_answer":
        return any(str(t).lower() in text.lower() for t in check.get("terms") or [])
    raise ToolFailure(f"failed: unknown check {kind} in the red-team suite")
