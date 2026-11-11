"""``pilot-incidents``: reproducible synthetic incidents with expected answers (FR-007 to FR-009;
research R-08).

Each incident carries the team, category and priority a correct triage gives, so routing accuracy
can be measured. Planted personal data (an e-mail at example.com and a phone number in the UK's
reserved drama range) appears only in the share of incidents asked for, and is listed in
``planted_pii``. Everything is labelled synthetic.
"""

import argparse
import json
import os
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from faker import Faker

from triage_agent.reference import Reference

EDGE_CASES = (
    "none",
    "unknown_service",
    "multi_service",
    "security",
    "missing_details",
    "duplicate",
    "out_of_scope",
)
WEIGHTS = (55, 8, 8, 10, 7, 6, 6)
URGENCY_PRIORITY = {"high": "P2", "medium": "P3", "low": "P4"}
IMPACT = "This is an outage for all users."
DEPARTMENTS = ("Finance", "HR", "Sales", "Operations", "Legal", "Marketing", "IT")
PERSONAS = ("new starter", "remote worker", "executive assistant", "field engineer", "analyst")
PROBLEMS = {
    "access": [
        "I am locked out of {name} after a password change.",
        "My account has no access to {name} since this morning.",
        "MFA prompts never arrive when I log in to {name}.",
    ],
    "hardware": [
        "The {name} screen flickers and the battery drains in an hour.",
        "{name} will not power on; the keyboard does not respond either.",
        "The dock for {name} stopped charging my laptop.",
    ],
    "software": [
        "{name} shows an error when I open it and then crashes.",
        "{name} fails after the latest update; the application freezes.",
        "Reports in {name} return an error since the update.",
    ],
    "network": [
        "The {name} connection drops every few minutes.",
        "{name} latency is very high and pages time out.",
        "No internet connection over {name} from the third floor.",
    ],
}
SECURITY = [
    "I clicked a phishing link and entered my password on a fake page.",
    "Antivirus reports malware on my laptop and files were encrypted (possible ransomware).",
    "I think customer data was leaked: a file was shared outside the company.",
    "There was a suspicious login to my account from another country.",
]
UNKNOWN_SERVICES = ("Quantum Planner", "Legacy Fax Gateway", "Holo Desk", "Ticket Printer 3000")
VAGUE = ("It is not working.", "Something is wrong, please help.", "Same issue as before.")
OUT_OF_SCOPE = (
    "Please order a birthday cake for the team on Friday.",
    "Could you recommend a good restaurant near the office?",
    "Where can I park my bicycle?",
)


def _incident(
    rng: random.Random, fake: Faker, reference: Reference, edge_case: str, n: int, seed: int
) -> dict[str, Any]:
    services = sorted(reference.services.values(), key=lambda s: s.id)
    urgency = rng.choice(("low", "medium", "high"))
    service = rng.choice(services)
    category = service.category if service.category in PROBLEMS else "software"
    title = f"{service.name} problem"
    description = rng.choice(PROBLEMS[category]).format(name=service.name)
    affected = service.id
    expected = {"team": service.owner, "category": category}
    if edge_case == "unknown_service":
        category = rng.choice(sorted(PROBLEMS))
        name = rng.choice(UNKNOWN_SERVICES)
        title, affected = f"{name} problem", name.lower().replace(" ", "-")
        description = rng.choice(PROBLEMS[category]).format(name=name)
        expected = {"team": reference.first_line, "category": category}
    elif edge_case == "multi_service":
        other = rng.choice([s for s in services if s.id != service.id])
        description += f" {other.name} is also affected."
    elif edge_case == "security":
        title, description = "Security concern", rng.choice(SECURITY)
        expected = {"team": reference.security, "category": "security"}
    elif edge_case == "missing_details":
        title, description, affected = "Help needed", rng.choice(VAGUE), ""
        expected = {"team": reference.first_line, "category": "software"}
    elif edge_case == "out_of_scope":
        title, description, affected = "Request", rng.choice(OUT_OF_SCOPE), ""
        expected = {"team": reference.first_line, "category": "software"}
    impact = edge_case == "none" and rng.random() < 0.12
    if impact:
        description += f" {IMPACT}"
    priority = "P1" if edge_case == "security" or impact else URGENCY_PRIORITY[urgency]
    first, last = fake.first_name(), fake.last_name()
    return {
        "incident_id": f"INC-{seed}-{n}",
        "title": title,
        "description": description,
        "reporter": {
            "name": f"{first} {last}",
            "department": rng.choice(DEPARTMENTS),
            "persona": rng.choice(PERSONAS),
        },
        "affected_service": affected,
        "urgency": urgency,
        "edge_case": edge_case,
        "expected": {**expected, "priority": priority},
        "synthetic": True,
        "planted_pii": [],
    }


def _plant(rng: random.Random, incident: dict[str, Any]) -> dict[str, Any]:
    first, last = incident["reporter"]["name"].lower().split(" ", 1)
    email = f"{first}.{last.replace(' ', '')}@example.com"
    phone = f"+44 7700 900{rng.randint(0, 999):03d}"
    return {
        **incident,
        "description": f"{incident['description']} Reach me at {email} or {phone}.",
        "planted_pii": [email, phone],
    }


def generate(
    seed: int, size: int, pii_share: float = 0.0, template: Path | None = None
) -> list[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security
    fake = Faker("en_GB")
    fake.seed_instance(seed)
    reference = Reference.load(template or default_template())
    found: list[dict[str, Any]] = []
    for n in range(1, size + 1):
        edge_case = (
            EDGE_CASES[n - 1] if n <= len(EDGE_CASES) else rng.choices(EDGE_CASES, WEIGHTS)[0]
        )
        if edge_case == "duplicate" and found:
            source = rng.choice(found)
            incident = {**source, "incident_id": f"INC-{seed}-{n}", "edge_case": "duplicate"}
        else:
            incident = _incident(rng, fake, reference, edge_case, n, seed)
        if pii_share and rng.random() < pii_share and not incident["planted_pii"]:
            incident = _plant(rng, incident)
        elif incident["planted_pii"] and not pii_share:
            incident = {**incident, "planted_pii": []}
        found.append(incident)
    return found


def default_template() -> Path:
    return Path(os.environ.get("PILOT_TEMPLATE", Path(__file__).resolve().parents[2] / "template"))


def write(incidents: Sequence[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(i, sort_keys=True) + "\n" for i in incidents))


def main() -> None:
    parser = argparse.ArgumentParser(prog="pilot-incidents", description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--pii-share", type=float, default=0.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write(generate(args.seed, args.size, args.pii_share), args.out)
    print(f"pilot-incidents: {args.size} incidents written to {args.out}")
