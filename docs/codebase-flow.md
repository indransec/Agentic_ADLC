# How the platform works, end to end

From a person submitting a use case to the lifecycle moving across terminals T0 to T9. For each step: which
component acts, why, what triggers it, and which tables it reads and writes. Detailed design lives in each package's
`README.md` under `src/adlc/` and in `docs/solution-architecture.md` (SA).

Table names are the SQLite tables created by `db/migrations/versions/0001_baseline.py`; one database file at
`ADLC_DB_PATH` (see `docs/run-without-docker.md`).

## 1. The processes

| Process | Package | Purpose | Database |
|---|---|---|---|
| `adlc-web` | `adlc.web` + `web/` | Serves the React app; forwards `/api` to the API unchanged | None |
| `adlc-api` | `adlc.api` | HTTP API: sign-in, sessions, every person's action | Yes |
| `adlc-orchestrator` | `adlc.orchestration` (+ `agents`, `policy`, `ledger`) | The worker: delivers events, runs automatic steps, fires timers and monitors | Yes |
| `adlc-knowledge` | `adlc.knowledge` | Read-only MCP server for grounding agents (enterprise documents, mocked) | None |
| `adlc-tools` | `adlc.tools.enterprise` | MCP servers for enterprise systems (eval store, ITSM, IAM, GRC…; mocked) | Yes |
| `adlc-pilot-bridge` | `adlc.tools.bridge` | MCP servers that act on the pilot agent being built (git, CI, harness, deploy…) | None |
| One-off steps | `alembic upgrade head` (migrate), `adlc-spec register`, `adlc-ledger verify` | Create the schema; register specs; verify the ledger | Yes |

The API and the orchestrator never call each other. **They communicate only through the database**: the API writes
a signal's result or an event; the worker picks it up.

## 2. Before any use case: specs are registered

| Step | Component | Reads | Writes |
|---|---|---|---|
| Validate | `adlc-spec validate` (`spec_toolkit`) | `adlc-specs/terminals/*.yaml`, `adlc-specs/shared/*.yaml`, prompts, playbooks, checklists | Nothing |
| Register | `adlc-spec register` | The same files | `spec_registry` (one row per terminal and version), `spec_catalogue` (shared catalogues), `spec_trigger` (which events open which terminal), `spec_outcome_route`, `spec_event_route`, `spec_timeline`, `spec_change_class`, `prompt_registry`, `playbook_registry` (with content hashes) |

Validation runs levels L1 to L5 (parse, JSON schema, single-spec rules, cross-spec and catalogue rules, version
bumps). At run time code reads specs only through `SpecRegistry`, never the YAML.

## 3. Submitting a use case

```
browser ──POST /api/usecases──► adlc-web ──► adlc-api ──► OrchestratorService.submit_usecase
```

| Step | Component | What happens | Tables |
|---|---|---|---|
| 1 | `adlc.api.auth` middleware | Resolves the session (cookie + CSRF, or bearer) to a person | None (sessions are signed tokens) |
| 2 | `routes/usecases.py` `submit` | Validates the body (name, intake text) | |
| 3 | `OrchestratorService.submit_usecase` | Checks a person (not an agent) is acting, and holds one of the **submitter roles**: the accountable roles of the terminals that `usecase.submitted` opens, read from the specs | `spec_trigger`, `spec_registry` |
| 4 | Same, one transaction | Creates `UC-nnnn`; **pins** the currently active version of every terminal spec to this use case; writes the event `usecase.submitted` | `sequence_counter`, `usecase`, `usecase_spec_pin`, `outbox_event` |

From here the API's work is done. Everything else is the orchestrator's.

## 4. The orchestrator worker loop

`adlc-orchestrator run` (`worker.py`) repeats, every `ADLC_POLL_INTERVAL`:

| Part | Module | Purpose | Tables |
|---|---|---|---|
| Deliver events | `outbox.py` → `router.py` | Takes undelivered events in order per use case; routes each in one transaction with its `processed_event` row, so a crash never half-delivers and a repeat is skipped. Retries 10 s, 1 min, 5 min, 15 min; dead letter after 5 failures | `outbox_event`, `processed_event` |
| Advance runs | `engine.advance()` | Runs the next automatic step of one run (prerequisites, build, controls, review, re-check) | See section 5 |
| Fire timers | `timers.py` | `escalate_after`, `clarification_sla`, `review_due` | `timer` |
| Evaluate monitors | `monitors.py` | Continuous terminals' monitors; a breached threshold raises `<terminal>.event.<name>` | `outbox_event`, `policy_decision` |
| Heartbeat | `worker.py` | Liveness for `/health` | `orchestrator_heartbeat` |

### Routing an event (`router.py`)

1. Ignore the event if the use case is no longer `active`.
2. Load the use case's **pinned** specs (`usecase_spec_pin`).
3. Follow the raising terminal's **event routes** (operational events): record immediate actions, write a follow-on
   event when its condition holds.
4. Find the **subscribers**: terminals whose pinned spec lists this event in its trigger (`on:`), plus a terminal the
   event names explicitly (a self-route rework or a resolver destination such as `owning_terminal`).
5. For each: **signal** the terminal's active run, or **open** a new run (`engine.open_in`).

### Opening a run (`engine.open_in`)

| Does | Tables |
|---|---|
| Run id `UC-nnnn/Tn/run-k`; spec version from the pin; mode (normal, evolve, retire) from the trigger | `terminal_run` |
| Counts rework cycles; sets `due_at` from the spec's timeline for the use case's risk tier | `terminal_run` |
| Records the profile version the run will read until it closes | `terminal_run.profile_version` |
| First transition `→ opened`; activity "opened" | `run_transition`, `run_activity` |
| Starts the `escalate_after` timer | `timer` |
| Over the rework limit: opens straight into **escalated** | `run_transition` |

## 5. Inside a terminal: the micro-orchestration of one run

Every terminal T0 to T9 runs the same state machine. No terminal-specific code exists (a test forbids terminal ids,
event names and role names in code).

```
opened ─► building ─► checking ─► reviewing ─► awaiting_sign_off ─► closed
  │           │  ▲         │                         │  ▲
  ▼           ▼  └─retry───┘                         │  └─ waiver rejected
blocked   awaiting_clarification                     ▼
                                        escalated ─► awaiting_sign_off
```

### How a step is applied

- **`states.py`** is a pure transition table: (state, signal) → new state + effects. It checks the **actor type**
  allowed to send each signal (section 8).
- **`engine.apply_in`** applies one signal per transaction: lock the run row → `transition()` → execute the effects →
  write `run_transition` and `run_activity`. The run's `version` increases with each change.
- **`engine.advance`** runs automatic steps: lease the run, **release the database connection**, call the policy
  engine, agent or reviewer, then apply the result with a version check. A result for a run that moved on is recorded
  as `stale`; an expired lease counts as an automatic retry.

### The steps

| State | Component | What it does | Reads | Writes |
|---|---|---|---|---|
| **opened** | Policy engine `evaluate` (`adlc.policy`) | Evaluates every **prerequisite** (CEL expressions from the spec) against evidence. A failed `block` one → **blocked**; a failed `warn` one is only recorded | Evidence (section 6) | `policy_decision` (one row per check, with inputs and reason) |
| **building** | Agent runtime (`adlc.agents.RuntimeAgentRunner`) | The terminal's agent produces the artifacts (below) | Context pack | `agent_attempt`, `model_call`, `knowledge_retrieval`, `tool_call`, `tool_result`, `artifact_version`, `content_blob`, `artifact_citation` |
| | | Or asks a **clarification** → `awaiting_clarification` until the addressed role answers (limit per spec) | | `clarification_round`, `clarification_answer`, `timer` |
| | | Or fails: retried up to the limit, then **escalated** (also on budget exceeded or no model available) | | `run_transition` |
| **checking** | Policy engine `evaluate` | Runs every **automated control** on the artifacts. A blocking failure sends the agent back (`building`, with the failed controls in its context) up to the retry limit, then escalates. A control with `awaits` (e.g. a change approval) does not send it back | Artifacts, evidence | `policy_decision`, `terminal_run.control_results` |
| **reviewing** | Reviewer (`adlc.agents.RuntimeReviewer`) | An **independent** model scores the checklist and recommends pass, rework or exception. It never sees the builder's reasoning | Checklist, artifacts, control results, clarifications | `checklist_result`, `model_call` |
| **awaiting_sign_off** | People, through the API (section 7) | Pass (until the sign-off rule's approvers are complete), rework, exception (+ waiver), terminate; edit artifacts (controls re-run before deciding) | | `sign_off`, `waiver`, `artifact_version` |
| **escalated** | People | The accountable role completes the work by hand, then it goes to sign-off; or terminates | | `artifact_version`, `run_transition` |
| **closed** | Engine `_close` | Section 7 | | |

### What runs inside the build step (`agents/runner.py`)

1. **Context pack** (`context.py`): the spec's agent prompt and playbooks (checked against their registered hashes),
   the use case (name, intake text, risk tier, mode), the trigger (and the rework comment and root cause when
   reworking), the previous run's artifacts, clarification answers, failed controls on a retry, and the evidence the
   prerequisites read. Untrusted text goes inside `<data>` blocks.
2. **Model gateway** (`gateway.py`): the spec names a **tier** (`reasoning`, `coding`, `standard`), never a model.
   `model_catalogue.yaml` gives the ordered models per `ADLC_MODEL_PROFILE`. Models without a key or not approved for
   the run's data class are skipped; fallback only on outages, never on refusals.
3. **Bounded loop**: step, token and time limits per tier (`limits.py`); cost recorded per call.
4. **Tools** (`tools.py` `ToolGate`): every tool call is **authorized first** (section 8), then sent to the knowledge
   server (grounding) or to the tools / pilot-bridge servers (acting) with a run token.
5. **Output validation** (`output.py`): artifacts must match the spec's artifact shapes; a mismatch gets a correction
   message, then the attempt fails.

## 6. Where use-case-specific details come from

Specs never contain use-case values. Each run gets them from these sources:

| Source | What it gives | Where it comes from | Table |
|---|---|---|---|
| **Pinned spec versions** | Which version of each terminal this use case follows, for its whole life | Pinned at submission | `usecase_spec_pin` |
| **Intake** | Name, free text, business owner (the submitter) | The submission | `usecase` |
| **Risk tier** | Selects timelines, sign-off rules, tiering controls and guardrail values | Emitted by T0 on pass; `medium` until set | `usecase.risk_tier` |
| **Use-case profile** | Values each terminal **emits** on pass (e.g. targets proposed by T1), versioned | Written at close | `profile_version` |
| **Parameters** (`param.<name>`) | Guardrail values for the tier, tightened by the profile where allowed (never loosened) | `guardrails.yaml` + profile; resolved when the run opens and **frozen** | `run_parameter_set` |
| **Previous terminals' evidence** (`T<n>.…`) | Status, signers, waivers, artifacts, emitted values of each terminal's latest closed run | Earlier runs | `terminal_run`, `artifact_version`, `content_blob`, `ledger_record`, `sign_off`, `waiver` |
| **Trigger context** | Why this run opened: rework comment, root cause, decision fields, re-entry terminal | The event that opened it | `terminal_run.trigger_context` |
| **Tool evidence** | Results recorded by real tool calls (CI, harness, red-team, observability) | MCP tool servers | `tool_call`, `tool_result`, `enterprise_record` |
| **Directory, catalogues** | Accounts and roles; shared catalogues | `ADLC_ACCOUNTS_FILE`; registered catalogues | `spec_catalogue` |
| **Synthetic** | Sources not built yet (`env`, `sbom`, `change`…) from `data/synthetic/`; every decision reading them is labelled `synthetic` | Files | `policy_decision` |

The policy engine's evidence provider (`policy/evidence.py`) assembles these for each check; the agent's context pack
uses the same records.

## 7. Moving across terminals

A terminal never calls the next one. **A run closes, writes an outcome event, and the router opens the next run.**

```
person decides (API) ─► OrchestratorService.decide ─► engine.apply_in ─► states._decide ─► engine._close
   ─► outbox_event "T2.pass" ─► worker delivers ─► router: subscribers of "T2.pass" ─► open_in(T3)
```

### Closing a run (`engine._close`, one transaction)

| Does | Tables |
|---|---|
| Final status; cancels timers | `terminal_run`, `timer` |
| Finds the route for the status (and root cause for rework) in the pinned spec | `spec_outcome_route` |
| On **pass**: computes **emitted values** (decision fields, artifacts, run values) | |
| Writes the **ledger record**: each artifact's version and hash, emitted references, profile version, `bound_to`; hash-chained to the previous record | `ledger_record`, `content_blob` |
| Writes the next **profile version** (pass or exception with emitted values) | `profile_version` |
| Sets the use case's **risk tier** when one is emitted | `usecase` |
| Writes the **outcome event** `Tn.<status>` (or `Tn.rework.<root_cause>`, `T9.reentry.Tn`) with comment, root cause, decision fields, waiver id, emitted values | `outbox_event` |
| Continuous terminal (T8): schedules the next review | `timer` |
| Terminating route or terminate: ends the lifecycle | `usecase.status` |

### Route kinds

| Outcome | Route | Next run |
|---|---|---|
| pass / exception | The next terminal (`route: T3`) | Opens there |
| | `continue` (T8) | The next review on schedule |
| | A template (`${T9.change_impact_assessment.reentry_terminal}`) | The terminal the artifact names |
| | An alternative chosen at sign-off | That destination |
| rework | `route_by_root_cause` (e.g. `design: T2`) | That terminal, with the comment in its trigger |
| | `owning_terminal` (a resolver) | The terminal chosen at sign-off |
| escalate | A human destination (`human_completion`, a board) | Same run, escalated |
| terminate | | The lifecycle ends |
| Operational event (`T8.event.drift`) | `event_routes` | E.g. T9 |

Ledger integrity: `ledger_record` rows are append-only (database triggers refuse UPDATE and DELETE); `adlc-ledger
verify` checks the hash chain and content (`verification_run`).

## 8. Identity and access

### People

| Check | Where | How |
|---|---|---|
| **Who is signed in** | `adlc.identity`, `adlc.api.auth` | Accounts in `ADLC_ACCOUNTS_FILE` (scrypt hashes); roles validated against `adlc-specs/shared/roles.yaml`. Sign-in issues a signed, expiring token: a bearer token for tools and tests, or an HttpOnly cookie plus CSRF value for the browser. Every endpoint needs a session except `PUBLIC_PATHS` (`/health`, `/auth/sign-in`) |
| **Who acts** | API | Always the signed-in person; a body naming an actor or role is refused |
| **Is it a person** | `OrchestratorService._human` | Decisions, answers, waivers and escalation completion are refused for non-human actors |
| **May this person do this** | `OrchestratorService` + `inbox/rules.py` | Roles come from the **pinned spec**: sign-off rule roles and required conditional roles (`min_approvers`, `plus` roles), `terminate`'s `set_by`, the exception's `set_by` (else accountable roles) for waivers (approver ≠ proposer), the clarification's addressed role, accountable roles for escalation and blocked runs, `ADLC_DEADLETTER_ROLE` for dead letters. The Inbox uses the same functions, so it never offers an action the operation would refuse |
| **Is the decision current** | Engine | The request sends `expected_version`; a changed run answers `409 stale` and records nothing |
| **Is the transition allowed** | `states.py` | The decision must be allowed in the current state (e.g. no pass while a waiver is pending or controls are re-running) |

### Agents, reviewer and orchestrator

| Check | Where | How |
|---|---|---|
| **Signal rights** | `states.ALLOWED_ACTOR` | Each signal has one allowed actor type: agent results from `agent:<run_id>`, review results from `reviewer:<run_id>`, prerequisite/control/timer signals from the orchestrator, decisions only from a human. Agents can never decide pass, exception or terminate (spec rule V-09) |
| **Agent and tool actions** | `policy.authorize` via `agents/tools.py` `ToolGate` | Every action of `agent:<run_id>` is decided: run scope (only its own run) → tool scopes (`mcp:<server>:<scope>` from the spec's `tool_scopes`, or `tool_scopes_by_mode`) → deny list → allow list → **default deny**. Each decision is a `policy_decision` row. Duty groups keep one terminal from both building and deploying (rule V-16) |
| **Tool servers** | `adlc.tools.token`, `mcp_app.py` | Each call carries a **run token**: HMAC-signed, five minutes, with the allowed scopes and **bound values** (e.g. the candidate hash from T3, the authorised hash from T6). The server verifies scope and bound values before acting, so an agent cannot deploy a package other than the one authorised |
| **Knowledge server** | `adlc.knowledge` | Bearer token; only the grounding scopes the spec declares; documents filtered by data class (fails closed) |
| **Models** | `agents/gateway.py` | Only models approved for the run's data class; keys from the environment, never logged |

## 9. Table map

| Area | Tables |
|---|---|
| Specs | `spec_registry`, `spec_catalogue`, `spec_trigger`, `spec_outcome_route`, `spec_event_route`, `spec_timeline`, `spec_change_class`, `prompt_registry`, `playbook_registry` |
| Use cases | `usecase`, `usecase_spec_pin`, `profile_version`, `sequence_counter` |
| Runs | `terminal_run`, `run_transition`, `run_activity`, `sign_off`, `waiver`, `clarification_round`, `clarification_answer`, `timer`, `run_parameter_set` |
| Events | `outbox_event`, `processed_event`, `dead_letter_action` |
| Policy | `policy_decision` |
| Agents | `agent_attempt`, `model_call`, `knowledge_retrieval`, `cost_alert` |
| Tools | `tool_call`, `tool_result`, `enterprise_record` |
| Ledger | `ledger_record`, `artifact_version`, `content_blob`, `file_object`, `artifact_attachment`, `artifact_citation`, `checklist_result`, `verification_run` |
| Health | `orchestrator_heartbeat` |
