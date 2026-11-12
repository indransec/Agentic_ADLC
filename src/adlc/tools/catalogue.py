"""The tools every MCP server offers (feature 010, contracts/tools-mcp.md).

One declaration per tool, read by both sides:
- the servers build their MCP tool list from it and bind a handler to each name;
- the platform describes tools to the model from it, drops every argument the model may not set,
  adds the bound values and knows which results are evidence.

Which process serves a server comes from the MCP registry (``host``), never from here.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# A tool whose scope is the bound environment (``pilot_env`` create and delete: the one
# environment scope the terminal's spec grants), never chosen by the model.
ENVIRONMENT_SCOPE = "{environment}"


@dataclass(frozen=True)
class Arg:
    name: str
    kind: str  # JSON schema type: string, integer, number, boolean, object, array
    description: str
    required: bool = False
    enum: tuple[str, ...] = ()
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.kind, "description": self.description}
        if self.enum:
            out["enum"] = list(self.enum)
        if self.max_length is not None:
            out["maxLength" if self.kind == "string" else "maxProperties"] = self.max_length
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        return out


@dataclass(frozen=True)
class ToolSpec:
    server: str
    name: str
    scope: str
    description: str
    args: tuple[Arg, ...] = ()
    bound: tuple[str, ...] = ()  # bound values the server requires (contracts/run-token.md)
    bound_optional: tuple[str, ...] = ()  # bound when the platform has them (e.g. test's package)
    evidence: str | None = None  # tools.tool_result kind, when the result is evidence
    limit_s: float = 10.0  # the server's time limit

    @property
    def full_name(self) -> str:
        return f"{self.server}_{self.name}"

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {a.name: a.schema() for a in self.args},
            "required": [a.name for a in self.args if a.required],
            "additionalProperties": False,
        }

    def model_args(self) -> Mapping[str, str]:
        return {a.name: a.description for a in self.args}


def _s(name: str, description: str, *, required: bool = False, **kw: Any) -> Arg:
    return Arg(name, "string", description, required, **kw)


def _i(name: str, description: str, lo: float, hi: float, *, required: bool = False) -> Arg:
    return Arg(name, "integer", description, required, minimum=lo, maximum=hi)


HASH = "a package hash, sha256:<64 hex>"
ENVIRONMENTS = ("dev", "test")
EVIDENCE_KINDS = (
    "ci",
    "harness",
    "redteam",
    "dlp",
    "deploy",
    "traffic",
    "kill_switch",
    "observability",  # 012: stage and health metrics are copied, then checked
    "monitoring",  # 012: the monitors configured
)

TOOLS: tuple[ToolSpec, ...] = (
    # ------------------------------------------------------------ pilot environments (US1)
    ToolSpec(
        "pilot_env",
        "create",
        ENVIRONMENT_SCOPE,
        "Create the pilot environment this terminal may use for a package. In dev you name the "
        "package hash; in test the use case's candidate package is used.",
        (
            _s("package_hash", f"dev only: {HASH}"),
            Arg("settings", "object", "declared settings only, e.g. {model_mode: simulated}"),
        ),
        bound=("environment",),
        bound_optional=("candidate_hash",),
        evidence="environment",
        limit_s=120,
    ),
    ToolSpec(
        "pilot_env",
        "status",
        "read",
        "The status of the dev or test environment.",
        (_s("environment", "dev or test", required=True, enum=ENVIRONMENTS),),
    ),
    ToolSpec(
        "pilot_env",
        "delete",
        ENVIRONMENT_SCOPE,
        "Tear down the environment this terminal may use.",
        bound=("environment",),
        evidence="environment",
        limit_s=60,
    ),
    ToolSpec(
        "pilot_env",
        "infra",
        "read",
        "The golden template's infrastructure definitions with their versions.",
        (_s("environment", "dev, test or prod-sim (optional)", enum=("dev", "test", "prod-sim")),),
    ),
    # ------------------------------------------------------------ build (US2)
    ToolSpec(
        "git",
        "list",
        "read",
        "List files on main or on this run's branch.",
        (_s("path", "folder (optional)", max_length=500), _s("ref", "main or branch")),
        bound=("branch",),
    ),
    ToolSpec(
        "git",
        "read",
        "read",
        "Read a file on main or on this run's branch.",
        (
            _s("path", "file path", required=True, max_length=500),
            _s("ref", "main or branch"),
        ),
        bound=("branch",),
    ),
    ToolSpec(
        "git",
        "write",
        "branch_write",
        "Write files of the fill layout on this run's branch as one commit.",
        (
            Arg("files", "object", "path to text, at most 20 files", required=True, max_length=20),
            _s("message", "commit message", required=True, max_length=500),
            _s("parent", "the commit id you last read (the branch head)"),
        ),
        bound=("branch",),
    ),
    ToolSpec(
        "git",
        "open_pull_request",
        "branch_write",
        "Open a pull request from this run's branch to main.",
        (
            _s("title", "title", required=True, max_length=200),
            _s("description", "description", max_length=5000),
        ),
        bound=("branch",),
    ),
    ToolSpec(
        "ci",
        "run",
        "run",
        "Validate, build and smoke-test the fill on this run's branch; returns each check and the "
        "package hash.",
        (_s("commit", "a commit on the branch (default: the head)"),),
        bound=("branch",),
        evidence="ci",
        limit_s=90,
    ),
    ToolSpec(
        "artifact_store",
        "read",
        "read",
        "A built package's manifest by hash.",
        (_s("package_hash", HASH, required=True),),
    ),
    ToolSpec(
        "artifact_store",
        "write",
        "write",
        "Store a named text (build notes); returns its sha256.",
        (
            _s("name", "name", required=True, max_length=200),
            _s("text", "text", required=True, max_length=50_000),
        ),
    ),
    ToolSpec(
        "prompt_registry",
        "write",
        "write",
        "Version a prompt or instruction text; returns its sha256.",
        (_s("text", "text", required=True, max_length=50_000),),
    ),
    ToolSpec(
        "prompt_registry",
        "read",
        "read",
        "A prompt or instruction text by sha256.",
        (_s("sha256", "sha256:<64 hex>", required=True),),
    ),
    # ------------------------------------------------------------ evaluate and assure (US3)
    ToolSpec("dataset_registry", "list", "read", "The approved datasets with their hashes."),
    ToolSpec(
        "harness",
        "run",
        "run",
        "Run a registered dataset against the candidate package in the test environment.",
        (_s("dataset_id", "a dataset id from the registry", required=True),),
        bound=("candidate_hash",),
        evidence="harness",
        limit_s=60,
    ),
    ToolSpec(
        "redteam_harness",
        "run",
        "run",
        "Run the fixed red-team suite against the candidate package in the test environment.",
        (Arg("categories", "array", "attack categories (optional; default all)"),),
        bound=("candidate_hash",),
        evidence="redteam",
        limit_s=60,
    ),
    ToolSpec(
        "dlp_scanner",
        "run",
        "run",
        "Scan the candidate's answers on a personal-data dataset; findings are masked.",
        (_s("dataset_id", "a dataset with planted personal data", required=True),),
        bound=("candidate_hash",),
        evidence="dlp",
        limit_s=60,
    ),
    # ------------------------------------------------------------ release (US4)
    ToolSpec(
        "cd",
        "deploy",
        "deploy",
        "Deploy the package authorised for release to prod-sim as the candidate.",
        bound=("authorised_hash",),
        evidence="deploy",
        limit_s=120,
    ),
    ToolSpec("cd", "status", "read", "Prod-sim's stable and candidate packages and its split."),
    ToolSpec(
        "traffic_manager",
        "set",
        "write",
        "Set prod-sim's split: shadow, canary at a share, or full.",
        (
            _s("mode", "shadow, canary or full", required=True, enum=("shadow", "canary", "full")),
            Arg("share", "number", "canary share 0-1", minimum=0, maximum=1),
        ),
        evidence="traffic",
    ),
    ToolSpec(
        "traffic_manager",
        "rollback",
        "write",
        "Send all traffic back to the stable package.",
        evidence="traffic",
    ),
    ToolSpec(
        "kill_switch",
        "invoke",
        "invoke",
        "Stop prod-sim answering with the pilot until a person releases it.",
        (_s("reason", "why", required=True, max_length=500),),
        evidence="kill_switch",
    ),
    # ------------------------------------------------------------ operate (US5)
    ToolSpec(
        "observability",
        "metrics",
        "read",
        "The pilot's metrics per package over a window.",
        (_i("window_s", "window in seconds", 60, 3600),),
        evidence="observability",
    ),
    ToolSpec(
        "observability",
        "traces",
        "read",
        "The pilot's spans (no incident text) by request id or the last minutes.",
        (
            _s("request_id", "a request id", max_length=200),
            _i("minutes", "the last N minutes", 1, 60),
            _i("limit", "at most N spans", 1, 50),
        ),
    ),
    ToolSpec(
        "monitoring",
        "configure",
        "configure",
        "Add a monitor for this use case.",
        (
            _s("metric", "a metric observability returns, e.g. routing_accuracy", required=True),
            _s("operator", "<, <=, > or >=", required=True, enum=("<", "<=", ">", ">=")),
            Arg("threshold", "number", "threshold", required=True),
            _i("window_s", "window in seconds", 60, 3600, required=True),
        ),
        evidence="monitoring",
    ),
    ToolSpec("monitoring", "read", "read", "This use case's monitors and fired events."),
    ToolSpec(
        "feedback",
        "read",
        "read",
        "Synthetic user ratings and comments for the pilot.",
        (_i("limit", "at most N", 1, 100),),
    ),
    # ------------------------------------------------------------ enterprise mocks (US6)
    ToolSpec(
        "eval_store",
        "read",
        "read",
        "This use case's evaluation, red-team and scan results, and notes.",
        (_s("kind", "harness, redteam or dlp (optional)", enum=("harness", "redteam", "dlp")),),
    ),
    ToolSpec(
        "eval_store",
        "write",
        "write",
        "Add a note (agent-authored) to this use case's evaluation records.",
        (
            _s("note", "note", required=True, max_length=10_000),
            _s("result_id", "the result it is about (optional)"),
        ),
    ),
    ToolSpec(
        "servicenow",
        "change_create",
        "change_create",
        "Create a change request.",
        (
            _s("summary", "summary", required=True, max_length=500),
            _s("window_start", "ISO date-time", required=True),
            _s("window_end", "ISO date-time", required=True),
            _s("risk", "low, medium or high", required=True, enum=("low", "medium", "high")),
            _s("plan", "implementation and backout plan", max_length=10_000),
        ),
    ),
    ToolSpec(
        "servicenow",
        "incident_create",
        "incident_create",
        "Raise an incident.",
        (
            _s("summary", "summary", required=True, max_length=500),
            _i("severity", "1 (highest) to 4", 1, 4, required=True),
            _s("description", "description", max_length=10_000),
        ),
    ),
    ToolSpec(
        "servicenow",
        "read",
        "read",
        "This use case's change requests or incidents.",
        (
            _s("kind", "change or incident", required=True, enum=("change", "incident")),
            _s("id", "a record id (optional)"),
        ),
    ),
    ToolSpec("cmdb", "read", "read", "Configuration items.", (_s("ci_id", "CI-<n> (optional)"),)),
    ToolSpec(
        "cmdb",
        "write",
        "write",
        "Create or update a configuration item.",
        (
            _s("ci_id", "CI-<n> to update (optional)"),
            Arg("attributes", "object", "attributes", required=True, max_length=50),
        ),
    ),
    ToolSpec(
        "agent_registry",
        "read",
        "read",
        "Agent registry entries.",
        (_s("agent_id", "AG-<n> (optional)"),),
    ),
    ToolSpec(
        "agent_registry",
        "write",
        "write",
        "Register or update an agent (name, version, package_hash, owner, status).",
        (
            _s("agent_id", "AG-<n> to update (optional)"),
            Arg("attributes", "object", "attributes", required=True, max_length=50),
        ),
    ),
    ToolSpec(
        "iam", "read", "read", "The use case's agent identities, tool scopes and revocations."
    ),
    ToolSpec(
        "iam",
        "revoke",
        "revoke",
        "Revoke the agent's identity or tool scopes.",
        (
            _s("what", "identity or tool_scopes", required=True, enum=("identity", "tool_scopes")),
            _s("reason", "why", required=True, max_length=500),
        ),
    ),
    ToolSpec(
        "grc",
        "write",
        "write",
        "File an assurance report.",
        (
            _s("title", "title", required=True, max_length=200),
            _s("report", "report", required=True, max_length=50_000),
        ),
    ),
    ToolSpec("grc", "read", "read", "Assurance reports.", (_s("report_id", "GRC-<n> (optional)"),)),
    ToolSpec(
        "control_library",
        "read",
        "read",
        "Security, privacy and RAI controls by id or topic.",
        (_s("control_id", "a control id"), _s("topic", "a topic")),
    ),
)


@dataclass(frozen=True)
class Catalogue:
    tools: Mapping[str, ToolSpec] = field(default_factory=dict)

    def for_server(self, server: str) -> list[ToolSpec]:
        return [t for t in self.tools.values() if t.server == server]

    def get(self, full_name: str) -> ToolSpec | None:
        return self.tools.get(full_name)


CATALOGUE = Catalogue({t.full_name: t for t in TOOLS})
