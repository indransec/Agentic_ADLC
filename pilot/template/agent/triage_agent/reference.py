"""The mocked tools' reference data: the service catalogue and the team directory."""

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    handles: str
    first_line: bool = False
    security: bool = False


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    owner: str
    category: str


@dataclass(frozen=True)
class Reference:
    teams: dict[str, Team]
    services: dict[str, Service]

    @property
    def first_line(self) -> str:
        return next(t.id for t in self.teams.values() if t.first_line)

    @property
    def security(self) -> str:
        return next(t.id for t in self.teams.values() if t.security)

    @classmethod
    def load(cls, template: Path) -> "Reference":
        yaml = YAML(typ="safe")
        teams = yaml.load((template / "reference" / "team_directory.yaml").read_text())["teams"]
        services = yaml.load((template / "reference" / "service_catalogue.yaml").read_text())
        return cls(
            {str(t["id"]): Team(**t) for t in teams},
            {str(s["id"]): Service(**s) for s in services["services"]},
        )

    def lookup_service(self, service_id: str) -> Service | None:
        """The ``service_catalogue`` tool."""
        return self.services.get(service_id)

    def lookup_team(self, team_id: str) -> Team | None:
        """The ``team_directory`` tool."""
        return self.teams.get(team_id)
