# Low-level design: Agentic ADLC platform

| | |
|---|---|
| Scope | The platform as built on branch `feature/sqlite` + feature 022 (React web app), 2026-11-25 |
| Audience | Engineers changing or operating the platform |
| Related | `docs/solution-architecture.md` (SA, the why), `docs/terminal-design-spec.md` (TDS, terminal content), `docs/codebase-flow.md` (narrative flow), `docs/api-reference.md` (every endpoint, generated), `docs/exception-outcome.md`, each package's `src/adlc/<package>/README.md`, `specs/<nnn>-<feature>/` (Spec Kit specs and contracts) |

---

## 1. Design principles applied in code

| Principle | How the code enforces it |
|---|---|
| Specs drive behaviour; no terminal-specific code | Terminal ids, event names, role ids and route names never appear in `src/adlc` (`tests/unit/test_no_hardcoded_values.py`). Every behaviour is read from the use case's **pinned** spec through `SpecRegistry` |
| Agents build, people decide | `states.ALLOWED_ACTOR`: only a human signal can decide; spec rule V-09 forbids agents pass, exception and terminate |
| Deterministic rules outside models | Prerequisites, controls and authorization are CEL expressions evaluated by the policy engine; every decision is recorded |
| Evidence is immutable and provable | Append-only tables (triggers), hash-chained ledger records, `adlc-ledger verify` |
| One transaction per state change | `engine.apply_in`: lock, transition, effects, history in one transaction; outcome event written in the same transaction (transactional outbox) |
| Fail closed | Policy errors, missing evidence, unknown data classes, unverifiable tokens all deny |
| Settings from the environment only | `pydantic-settings` classes in `adlc.config.settings`; no secrets in files or logs |

---

## 2. Deployment view

### 2.1 Processes

| Process (console script) | Package | Network role | Database | Port setting (default) |
|---|---|---|---|---|
| `adlc-web` | `adlc.web` | Serves `web/dist`; proxies `/api/*` to the API | No | `ADLC_UI_PORT` (8501) |
| `streamlit` (legacy, until 022 cutover) | `adlc.ui` | Old web app | No | `ADLC_LEGACY_UI_PORT` (8502) |
| `adlc-api` | `adlc.api` | HTTP API (FastAPI + uvicorn) | Yes | `ADLC_API_PORT` (8000) |
| `adlc-orchestrator run` | `adlc.orchestration` (+ `agents`, `policy`, `ledger`, `inbox`) | Background worker | Yes | none |
| `adlc-knowledge` | `adlc.knowledge` | MCP server, grounding (read-only) | No | `ADLC_KNOWLEDGE_PORT` (8020) |
| `adlc-tools` | `adlc.tools.enterprise` | MCP servers, enterprise systems (mocks) | Yes | `ADLC_TOOLS_PORT` (8030) |
| `adlc-pilot-bridge` | `adlc.tools.bridge` | MCP servers acting on the pilot | No (volume `bridge-data`) | `ADLC_BRIDGE_PORT` (8040) |
| Phoenix | `deploy/phoenix` | Trace collector (OTLP) and UI | Own | 6006 |
| Pilot hosts | `pilot/` (own uv project) | dev, test, prod-sim, traffic, lab | No | 8101–8103, 8200, 8300 |
| One-off | `alembic upgrade head`, `adlc-spec register`, `adlc-account`, `adlc-ledger verify/trace`, `adlc-replay`, `adlc-demo`, `adlc-tools-probe` | | Yes | |

Run modes: Docker Compose (`deploy/compose.yaml`, `make up`), or without Docker (`deploy/Procfile.local` with
honcho, `make local`; `docs/run-without-docker.md`).

### 2.2 Communication

```
browser ─HTTP─► adlc-web ─HTTP /api─► adlc-api ─SQL─┐
                                                    ├─► SQLite file (ADLC_DB_PATH, WAL)
adlc-orchestrator ─SQL──────────────────────────────┤
adlc-tools ─SQL─────────────────────────────────────┘
adlc-orchestrator ─MCP (HTTP, run token)─► adlc-tools, adlc-pilot-bridge ─HTTP─► pilot hosts
adlc-orchestrator ─MCP (HTTP, bearer)───► adlc-knowledge
adlc-orchestrator ─HTTPS─► model providers (via LiteLLM)
every Python process ─OTLP─► Phoenix
```

- The API and the orchestrator **never call each other**: the API writes rows (decisions, events); the worker polls.
- `adlc-web` holds no database or session settings; it forwards cookies and the CSRF header to the API.
- The knowledge server imports nothing from orchestration, ledger, policy, agents or API (boundary test).

---

## 3. Module design

### 3.1 Package map

| Package | Responsibility | Key types |
|---|---|---|
| `adlc.config` | Settings per process, validation at start-up | `DatabaseSettings`, `RuntimeSettings`, `Settings` (API), `OrchestratorSettings`, `KnowledgeSettings`, `ToolsSettings`, `BridgeSettings`, `UiSettings` |
| `adlc.db` | SQLite engine: WAL, busy timeout, `BEGIN IMMEDIATE` for explicit transactions, type adapters | `database_engine`, `open_engine`, `write_independently`, `wait_for_database` |
| `adlc.identity` | Accounts, password hashing, sessions | `IdentityProvider` (Protocol), `LocalIdentityProvider`, `Person`, `Grant` |
| `adlc.spec_toolkit` | Validate (L1–L5, ~60 rules) and register specs; read registered specs | `SpecRegistry`, `SqlSpecRegistry`, `InMemorySpecRegistry`, `RegistryEntry`, `OutcomeRoute`, `TerminalRef` |
| `adlc.orchestration` | State machine, engine, routing, outbox, timers, monitors, worker, human operations | `RunState`, `SignalKind`, `Signal`, `transition()`, `SqlTerminalRun`, `SqlRouter`, `OutboxProcessor`, `TimerLoop`, `MonitorEvaluator`, `Orchestrator`, `OrchestratorService` |
| `adlc.policy` | CEL evaluation, ~60 predicates, evidence, parameters, authorization | `SqlPolicyEngine`, `EvidenceProvider`, `resolve()` (parameters), `authorization.decide` |
| `adlc.agents` | Agent runtime: context, gateway, bounded loop, tools, reviewer, replay | `RuntimeAgentRunner`, `RuntimeReviewer`, `RoutingGateway`, `LiteLLMTransport`, `ToolGate`, `KnowledgeTool`, `McpTool` |
| `adlc.ledger` | Content store, artifact versions, ledger content and hash, profile, verification | `LedgerService`, `FileStore`, `Verifier`, `SqlProfileSource` |
| `adlc.inbox` | Read side: inbox items, run detail, decision form, role rules, changes, proposed events | `InboxService`, `build_form`, `rules.*`, `ChangeService` |
| `adlc.dashboard` | Read-only journey, KPIs, portfolio, activity, run timeline | `DashboardService` |
| `adlc.api` | HTTP layer: auth middleware, routes, response schemas, error mapping, OpenAPI docs | `create_app`, `install_auth`, `install_errors`, `ApiModel`, `document()` |
| `adlc.web` | Static server + `/api` proxy for the React app | `create_app(UiSettings)`, `SecurityHeaders`, `BuiltAssets` |
| `adlc.knowledge` | Knowledge MCP server over a document folder | `documents`, `search` (BM25), `scope`, `server` |
| `adlc.tools` | Tool catalogue, MCP registry, run tokens, MCP servers (enterprise mocks, pilot bridge), client | `Catalogue`, `ToolSpec`, `Registry`, `Claims`, `issue/sign/verify`, `mcp_app` |
| `adlc.observability` | Logging and OpenTelemetry setup, span helpers | `configure_logging`, `setup_tracing`, `span` |
| `adlc.demo` | Scripted end-to-end demo driver | `DemoDriver`, `load_script` |
| `adlc.ui` | Legacy Streamlit app (removed at 022 cutover) | |
| `web/` | React + TypeScript app (Vite) | see section 12 |

### 3.2 Orchestration internals (`src/adlc/orchestration`)

| Module | Contents |
|---|---|
| `states.py` | **Pure** transition table: `RunState`, `ActorType`, `SignalKind`, `Signal`, `TransitionContext`, effect dataclasses, `Outcome`, `ALLOWED_ACTOR`, `transition(state, signal, ctx) -> Outcome`, `sign_off_complete` |
| `engine.py` | `SqlTerminalRun`: `open_in`, `apply`, `apply_in`, `context`, `advance`, effect execution (`_effect`), `_close`, `_write_ledger`, `_escalate`, `_propose_waiver`, `_store_artifacts`, build/review/check step calls |
| `store.py` | All SQL of the package; every function takes the caller's `Connection` |
| `spec_view.py`, `routing.py` | Pure reads over a pinned spec (prerequisites, controls, roles, outcomes, timelines); routing decisions (subscribers, event types, run mode, rework counting, templates, emitted values) |
| `router.py` | `SqlRouter.handle(conn, event)`: event routes, subscribers, open or signal; `open_review` |
| `outbox.py` | `OutboxProcessor`: ordered, idempotent delivery with retries and dead letters |
| `timers.py` | `TimerLoop.fire_next/drain` |
| `monitors.py` | `MonitorEvaluator.tick_if_due/tick` |
| `service.py` | `OrchestratorService`: submit, decide, answer, waiver decision, escalation completion, dead-letter list/requeue, awaited action done |
| `worker.py`, `__main__.py` | `Orchestrator` (`drain`, `run_once`, `run_forever`), `build_orchestrator`, `adlc-orchestrator run|health` |
| `interfaces.py`, `stubs.py` | Protocols `PolicyEngine`, `AgentRunner`, `Reviewer`, `Clock`; `EvalContext`, `BuildContext`, `ReviewContext`, result types; scriptable stubs for tests |
| `ids.py`, `durations.py`, `ledger.py`, `tracing.py` | Identifiers, TDS durations and time scale, ledger record construction, spans |

### 3.3 Internal interfaces

```python
class PolicyEngine(Protocol):
    def evaluate(self, expression: str, context: EvalContext) -> EvalResult: ...   # passed, value, reason, synthetic
    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool: ...

class AgentRunner(Protocol):
    def build(self, context: BuildContext) -> AgentResult: ...
    # Artifacts | Clarification | BudgetExceeded | AttemptFailed | ModelUnavailable

class Reviewer(Protocol):
    def review(self, context: ReviewContext) -> ReviewResult: ...
    # Recommendation | Clarification | AttemptFailed | ModelUnavailable

class IdentityProvider(Protocol):
    def sign_in(self, account_name: str, password: SecretStr) -> Grant: ...
    def current_person(self, token: str) -> Person: ...
    def roles(self, account_name: str) -> frozenset[str]: ...
    def sign_out(self, token: str) -> None: ...

class Clock(Protocol):
    def now(self) -> datetime: ...
```

`EvalContext(terminal_id, check_id, run_id, usecase_id, attempt=None)`; `check_id` is the prerequisite or control id,
or `plus:<role>`, `external:<body>`, `then_when:<event>`, or a monitor id.

`BuildContext(run_id, terminal_id, spec, usecase{usecase_id, name, intake_text, risk_tier, mode}, trigger,
previous_artifacts, clarifications, attempt, failed_controls)`.

`ReviewContext(run_id, terminal_id, checklist_items, artifacts, control_results, clarifications)`; the builder's
reasoning is never included.

---

## 4. Data design

One SQLite file (`ADLC_DB_PATH`), WAL journal, schema by Alembic (`db/migrations/versions/0001_baseline.py`, a
squash of the earlier PostgreSQL migrations). Types: `timestamptz` (ISO 8601 UTC text), `jsonb` (JSON text),
`boolean`, `numeric`, `uuid`, `date`, converted by `adlc.db.engine`.

### 4.1 Identifiers

| Entity | Format | Source |
|---|---|---|
| Use case | `UC-0001` | `sequence_counter` |
| Run | `UC-0001/T3/run-2` (contains `/`) | use case + terminal + run number |
| Clarification | `<run id>/clar-<n>` | |
| Waiver | `WVR-0001` | `sequence_counter` |
| Event | UUID v7 | `ids.uuid7()` |
| Correlation | `UC-0001/lifecycle` | one per use case |
| Content | `sha256:<64 hex>` | normalised JSON or file bytes |
| Actors | person `account_name`; `agent:<run_id>`, `reviewer:<run_id>`, `orchestrator` | |

### 4.2 Tables

`!` = NOT NULL. **A** = append-only (triggers refuse UPDATE and DELETE).

**Specs** (written by `adlc-spec register`)

| Table | Key | Columns | Notes |
|---|---|---|---|
| `spec_registry` | `spec_registry_id` | terminal_id!, version! (semver), status! (active/deprecated/retired), schema_version!, spec_yaml!, spec_json!, content_hash!, trigger_events!, emitted_events!, registered_at!, deprecated_at, retired_at | Status only moves forward; a pinned version is never retired; never deleted |
| `spec_catalogue` | `spec_catalogue_id` | catalogue_name!, version!, status!, content_json!, content_hash!, registered_at!, deprecated_at, retired_at | Shared catalogues (roles, guardrails, mcp_servers…) |
| `spec_trigger` | (spec_registry_id, event_type) | | Which events open a terminal. A |
| `spec_outcome_route` | `spec_outcome_route_id` | spec_registry_id!, outcome_status!, root_cause, destination_kind!, destination!, alternatives!, requires!, recheck_at!, set_by!, notify!, condition | A |
| `spec_event_route` | (spec_registry_id, event_type) | destination_kind!, destination!, immediate!, then_destination, notify!, condition | Operational events. A |
| `spec_timeline` | (spec_registry_id, risk_tier) | expected_duration, continuous!, reminder_after!, escalate_after, escalate_at_window_end!, max_rework_cycles!, clarification_sla!, max_clarification_rounds!, max_auto_retries, retirement_duration | A |
| `spec_change_class` | (spec_registry_id, change_class) | reentry_terminal!, path!, retrospective!, within, alternative | T9 change classes. A |
| `prompt_registry`, `playbook_registry` | id | prompt_id/playbook_id!, version!, path!, content_hash!, registered_at! | Agents refuse a file whose hash differs. A |

**Use cases**

| Table | Key | Columns | Notes |
|---|---|---|---|
| `usecase` | `usecase_id` | name!, intake_text!, submitted_by!, risk_tier (low/medium/high), status! (active/closed), created_at!, closed_at | Only tier, status and closing time may change |
| `usecase_spec_pin` | (usecase_id, terminal_id) | version!, pinned_at!, pinned_reason! | Written at submission |
| `profile_version` | (usecase_id, version) | profile_values!, source_run_id!, created_at! | Merged emitted values. A |
| `sequence_counter` | `name` | value!, max_value! | Numbering |

**Runs**

| Table | Key | Columns | Notes |
|---|---|---|---|
| `terminal_run` | `run_id` | usecase_id!, terminal_id!, run_number!, spec_version!, state!, return_state, mode! (normal/evolve/retire), trigger_event_id, trigger_event_type!, trigger_context!, rework_count!, auto_retries!, clarification_rounds!, artifacts! (latest content), control_results!, recommendation, received_events!, pending_waiver_id, escalation_trigger, escalation_destination, final_status, **version!**, **lease_until**, opened_at!, due_at, closed_at, profile_version!, approvals_after_sign_off_id, controls_pending!, model_unavailable_since | A closed run is frozen; identity columns never change; never deleted |
| `run_transition` | id | run_id!, from_state, to_state!, signal_kind!, actor_type!, actor_id!, reason, at! | Every transition. A |
| `run_activity` | id | run_id!, step!, actor_type!, actor_id!, started_at!, ended_at!, outcome!, detail! | Timeline (route, build, controls, review, sign_off…). A |
| `sign_off` | id | run_id!, role!, person!, decision!, comment, root_cause, reason_differs, target_terminal, fields!, signed_at! | A |
| `waiver` | `waiver_id` | run_id!, waiver_owner, compensating_control, expiry (date), recheck_at!, requires!, status! (pending/approved/rejected), proposed_by!, decided_by, decision_comment, proposed_at!, decided_at | Decided once; never deleted |
| `clarification_round` | `clarification_id` | run_id!, asked_by!, addressed_role!, questions!, looked_in!, asked_at! | A |
| `clarification_answer` | `clarification_id` | answered_by!, answers!, answered_at! | A |
| `timer` | id | run_id!, kind! (escalate_after/clarification_sla/review_due), due_at!, fired_at, cancelled_at, created_at! | |
| `run_parameter_set` | `run_id` | risk_tier!, guardrail_version!, parameters!, rejected!, resolved_at! | Frozen per run. A |

**Events**

| Table | Key | Columns | Notes |
|---|---|---|---|
| `outbox_event` | `event_id` (UUID v7) | event_type!, usecase_id, correlation_id!, causation_run_id, payload!, created_at!, attempts!, next_attempt_at!, processed_at, dead_lettered_at, last_error | Content never changes (trigger); only delivery columns |
| `processed_event` | `event_id` | processed_at! | Idempotency |
| `dead_letter_action` | id | event_id!, action!, actor!, at! | Re-queue history. A |

**Policy, agents, tools** (all A)

| Table | Columns |
|---|---|
| `policy_decision` | kind! (evaluate/authorize), run_id, usecase_id, terminal_id, check_id!, rule!, actor, passed!, value, reason!, inputs!, synthetic!, fail_safe!, duration_ms!, decided_at!, attempt |
| `agent_attempt` | run_id!, kind! (build/review), attempt!, agent_id!, agent_version!, implementation!, prompt_hash, playbook_hashes!, context_hash!, steps!, tokens_in!, tokens_out!, cost_usd, corrections!, outcome!, limit_reached, reason, started_at!, ended_at! |
| `model_call` | agent_attempt_ref!, run_id!, usecase_id!, terminal_id!, agent_id!, tier!, entry_index!, provider!, model!, prompt_hash, context_hash!, tokens_in!, tokens_out!, usage_estimated!, cost_usd, cost_known!, latency_ms!, outcome!, reason, fallback!, tried!, called_at! |
| `knowledge_retrieval` | run_id!, attempt!, step!, source!, operation!, request!, document!, section!, content_hash!, data_class!, synthetic!, retrieved_at! |
| `cost_alert` | usecase_id!, level_usd!, total_usd!, recorded_at! |
| `tool_call` | run_id!, usecase_id!, terminal_id!, attempt!, step!, tool!, server!, scope!, arguments_sha256!, outcome!, reason!, duration_ms!, at! |
| `tool_result` | tool_call_id!, run_id!, usecase_id!, terminal_id!, kind!, package_hash, result!, result_sha256!, at! |
| `enterprise_record` | system!, kind!, record_id!, version!, usecase_id!, run_id!, terminal_id!, body!, at! (mock ITSM/CMDB/GRC records; a change = a new version) |

**Ledger** (all A)

| Table | Key | Columns |
|---|---|---|
| `ledger_record` | id | ledger_key!, content_hash!, previous_record_hash, written_at!, run_id, usecase_id, content_json |
| `content_blob` | `content_hash` | body!, size!, stored_at! |
| `file_object` | `content_hash` | size!, media_type!, stored_at! (bytes in the `FileStore` under `ADLC_FILE_STORE_DIR`) |
| `artifact_version` | (run_id, artifact_id, version) | content_hash!, producer_type!, producer_id!, attempt, derived_from_version, schema_valid!, created_at! |
| `artifact_attachment` | (run_id, artifact_id, version, content_hash) | file_name!, media_type!, size! |
| `artifact_citation` | id | run_id!, artifact_id!, version!, row_index, source!, document!, section!, content_hash!, knowledge_retrieval_id!, cited_at! |
| `checklist_result` | id | run_id!, attempt!, item_id!, score, finding, recorded_at! |
| `verification_run` | id | actor!, scope!, started_at!, finished_at!, records_checked!, breaks!, verified! |

**Health**: `orchestrator_heartbeat` (worker_id, beat_at).

### 4.3 Integrity guarantees (78 triggers)

- `<table>_no_update`, `<table>_no_delete` on every append-only table.
- `spec_registry_status_only` / `_status_forward` / `_pinned`, `spec_catalogue_status_only` / `_status_forward`.
- `terminal_run_closed` (a closed run is frozen), `terminal_run_identity`, `terminal_run_no_delete`.
- `usecase_fixed`, `waiver_decided_once`, `outbox_event_content`.
- SQLite has no database roles: a process with file access could drop a trigger; the ledger hash chain still detects
  any change (`adlc-ledger verify`).

---

## 5. Run state machine

### 5.1 States and actors

| State | Kind | Who moves it on |
|---|---|---|
| `opened` | automatic | orchestrator (prerequisites) |
| `building` | automatic | agent |
| `checking` | automatic | orchestrator (controls) |
| `reviewing` | automatic | reviewer |
| `blocked` | waiting | an event (re-check) or terminate |
| `awaiting_clarification` | waiting | the addressed role's answer, or the SLA timer |
| `awaiting_sign_off` | waiting | people (decide, waiver, edit) |
| `escalated` | waiting | the accountable role (complete) or terminate |
| `closed` | final | |

`ALLOWED_ACTOR`: `prerequisites_result`, `event_received`, `controls_result`, `timer`, `open_escalated`,
`step_interrupted` → orchestrator; `agent_result` → agent; `review_result` → reviewer; `clarification_answered`,
`decide`, `waiver_decision`, `escalation_completed` → human. Any other actor type is `InvalidTransition`. A closed
run refuses every signal.

### 5.2 Transition table (`states.transition`)

| From | Signal (payload) | Guard | To | Effects |
|---|---|---|---|---|
| any open | `lifecycle_ended` | | closed | CancelAllTimers, CloseRun(terminate) |
| any open | `timer` escalate_after | not escalated | escalated | Escalate(timer) |
| awaiting_clarification | `timer` clarification_sla | | escalated | Escalate(clarification_sla) |
| any open | `event_received` | | same (blocked → **opened**) | RecordEvent |
| automatic | `step_interrupted` | retries < max | same | IncrementAutoRetry |
| automatic | `step_interrupted` | retries ≥ max | escalated | Escalate(retry_limit) |
| opened | `open_escalated` | | escalated | Escalate(trigger, e.g. rework_limit) |
| opened | `prerequisites_result` | met | building | |
| opened | `prerequisites_result` | not met | blocked | |
| building | `agent_result` artifacts | | checking | StoreArtifacts |
| building | `agent_result` clarification | rounds < max | awaiting_clarification | RecordClarification(agent), SetReturnState(building), StartTimer(clarification_sla) |
| building | `agent_result` clarification | rounds ≥ max | escalated | Escalate(clarification_limit) |
| building | `agent_result` budget_exceeded | | escalated | Escalate(budget) |
| building | `agent_result` failed | retries < max | building | IncrementAutoRetry |
| building | `agent_result` failed | retries ≥ max | escalated | Escalate(retry_limit) |
| building | `agent_result` model_unavailable | | escalated | Escalate(model_unavailable) |
| checking | `controls_result` passed | | reviewing | StoreControls |
| checking | `controls_result` failed | retries < max | building | StoreControls, IncrementAutoRetry |
| checking | `controls_result` failed | retries ≥ max | escalated | StoreControls, Escalate(retry_limit) |
| reviewing | `review_result` recommendation | | awaiting_sign_off | StoreRecommendation |
| reviewing | `review_result` clarification | as above | awaiting_clarification | (return state reviewing) |
| reviewing | `review_result` failed / model_unavailable | | escalated | Escalate(reviewer_failed / model_unavailable) |
| awaiting_clarification | `clarification_answered` | return state set | return state | CancelTimer(clarification_sla), SetReturnState(None) |
| awaiting_sign_off | `decide` pass | no pending waiver, controls not pending, no awaited control, role allowed | awaiting_sign_off or **closed** when `sign_off_complete` | RecordSignOff(pass) [+ CloseRun(pass)] |
| awaiting_sign_off | `decide` rework | no pending waiver | closed | RecordSignOff(rework), CloseRun(rework) |
| awaiting_sign_off | `decide` exception | no pending waiver, controls not pending | awaiting_sign_off | RecordSignOff(exception), ProposeWaiver |
| blocked / escalated / awaiting_sign_off | `decide` terminate | | closed | RecordSignOff(terminate), CloseRun(terminate) |
| awaiting_sign_off | `waiver_decision` approve | pending waiver | closed | DecideWaiver(approve), CloseRun(exception) |
| awaiting_sign_off | `waiver_decision` reject | pending waiver | awaiting_sign_off | DecideWaiver(reject) |
| escalated | `escalation_completed` | | awaiting_sign_off | StoreArtifacts |
| awaiting_sign_off / escalated | `artifact_edited` | | same | StoreArtifacts, ClearApprovals, [WithdrawWaiver], [SetControlsPending(true) at sign-off] |
| awaiting_sign_off / escalated | `controls_rechecked` | | same | StoreControls, SetControlsPending(false) |
| awaiting_sign_off | `evidence_changed` | awaited controls, not pending | same | SetControlsPending(true) |

`sign_off_complete(ctx, approvals)`: distinct people holding a rule role ≥ `min_approvers` **and** every required
`plus` role covered. The same person passing twice counts once.

### 5.3 Effects (executed by `engine._effect` in the same transaction)

| Effect | Writes |
|---|---|
| StoreArtifacts | `artifact_version`, `content_blob`, `artifact_citation`, `terminal_run.artifacts` |
| StoreControls | `terminal_run.control_results` |
| StoreRecommendation | `terminal_run.recommendation`, `checklist_result` |
| RecordSignOff | `sign_off` |
| ProposeWaiver / DecideWaiver / WithdrawWaiver | `waiver`, `terminal_run.pending_waiver_id` |
| RecordClarification | `clarification_round` |
| Start/CancelTimer, CancelAllTimers | `timer` |
| Escalate | `terminal_run.escalation_*`, `outbox_event` `<T>.escalate` |
| CloseRun | section 6.5 |
| IncrementAutoRetry, SetReturnState, ClearApprovals, SetControlsPending, RecordEvent | `terminal_run` columns |

After the effects: `run_transition` and `run_activity` rows; `terminal_run.version` + 1.

---

## 6. Key algorithms

### 6.1 Submit (`OrchestratorService.submit_usecase`)

1. Actor must be human; name 1–200 characters.
2. Actor must hold a **submitter role** = accountable roles of the terminals subscribed to `usecase.submitted`.
3. One transaction: active spec versions (refuse if none); `UC-nnnn`; insert `usecase`; insert one
   `usecase_spec_pin` per terminal; insert `outbox_event` `usecase.submitted`.

### 6.2 Worker round (`worker.Orchestrator`)

```
run_forever: loop { run_once(); wait ADLC_POLL_INTERVAL }        # errors logged, retried next round
run_once:    monitors.tick_if_due(); drain(); beat heartbeat
drain:       repeat { outbox.drain(); while runs.advance(); timers.drain() } until a pass does nothing
             (10,000 passes without settling → error)
```

### 6.3 Outbox delivery (`outbox.py`)

1. `BEGIN IMMEDIATE`; take the oldest due event (`next_attempt_at ≤ now`, not processed, not dead-lettered) of a use
   case **with no older pending event** (per-use-case order).
2. If `processed_event` has it: mark processed (duplicate), commit.
3. Savepoint; `router.handle(conn, event)`; insert `processed_event`; set `processed_at`; commit.
4. On error: roll back to the savepoint; `attempts + 1`; `last_error`; `next_attempt_at = now + delay`
   (10 s, 1 min, 5 min, 15 min, time-scaled); the 5th failure sets `dead_lettered_at`.
5. Dead letters: listed and re-queued by the CoE role (`ADLC_DEADLETTER_ROLE`), recorded in `dead_letter_action`.

### 6.4 Routing (`router.SqlRouter.handle`)

1. Use case missing or not `active` → ignore (processed).
2. Load pinned specs.
3. `_event_route`: for operational events, follow the raising terminal's `event_routes` (immediate actions recorded;
   a `then` event written when `then_when` holds via `policy.evaluate`).
4. Targets = `routing.subscribers(pinned, event_type)` ∪ the payload's `target_terminal` (self-route, resolver).
5. For each target: active run → `event_received` signal; otherwise `engine.open_in`.

### 6.5 Open and close a run

**`open_in`**: run number = history + 1; mode from trigger; rework count from history; `due_at` from the tier's
`expected_duration` (time-scaled); current profile version; `run_transition` (→ opened) and `run_activity`; timer
`escalate_after`; over `max_rework_cycles` → `open_escalated`.

**`_close`** (on CloseRun):
1. `final_status`, `closed_at`; cancel timers.
2. Route = `registry.outcome_route(terminal, status, root_cause, spec_version)`.
3. pass/exception: an `alternative` field, a template route (`${T9.….reentry_terminal}` resolved from artifacts), or
   a special destination (`continue`, terminating).
4. pass or exception: the outcome's own emitted values (`routing.emitted_values(..., status)`: decision fields, for an
   exception the fields kept with its waiver; artifacts; run values). V-39 makes an exception emit at least what a pass does.
5. rework: self-route or resolver (`target_terminal`).
6. Ledger record (6.6); `profiles.on_close` (next `profile_version` on pass/exception with emitted values); notified
   bodies (board/external approvals recorded as notifications).
7. `outbox_event` `routing.outcome_event_type(...)` (`Tn.pass`, `Tn.rework.<cause>`, `T9.reentry.Tn`…) with comment,
   root cause, decision fields, target terminal, waiver id, emitted values.
8. Emitted `risk_tier` → `usecase.risk_tier`. Continuous terminal → schedule review. Terminating → end the
   lifecycle (`usecase.status = closed`, `lifecycle_ended` to every open run).

### 6.6 Ledger record and chain

- `ledger_key` from the spec's ledger key pattern (use case, run).
- Content version 2 (`ledger.content.build_v2`): run, use case, terminal, spec version and hash, trigger, final
  status, decisions, recommendation, control results, clarifications, waiver, emitted references (with versions and
  hashes), profile version, artifacts (id, version, content hash, producer, attachments), `bound_to` (package hash).
- `content_hash = sha256(canonical JSON)`; `previous_record_hash` = the use case's latest record hash, read after
  locking the use case row (one chain per use case).
- `adlc-ledger verify` recomputes every hash and link; results in `verification_run`.

### 6.7 Automatic step (`engine.advance`)

1. `BEGIN IMMEDIATE`; `lease_next_automatic`: oldest run in an automatic state, or at sign-off/escalated with
   `controls_pending`, whose `lease_until` is null or past; set `lease_until = now + ADLC_LEASE`. An expired lease
   on an automatic state ⇒ `step_interrupted` first.
2. Read inputs on the connection (`_step`), **release the connection**.
3. Run the step: opened/`controls_pending` → policy checks; building → `agent.build`; reviewing → `reviewer.review`;
   checking → controls.
4. `apply` the resulting signal with `expected_version` = the version read in 1. A moved-on run ⇒ recorded `stale`.

### 6.8 Prerequisites and controls

- Prerequisites: `policy.evaluate(expr, EvalContext(..., check_id=PRE-…))` for each; failed `on_missing: block` ⇒
  `blocked_ids`; failed `warn` ⇒ `warned_ids`; `met = not blocked_ids`.
- Controls: each automated control evaluated; result `{id, passed, blocking, awaits, reason, synthetic}`; failed
  blocking without `awaits` ⇒ back to building; `awaits` ⇒ sign-off where pass is refused until it passes
  (`evidence_changed` re-runs it).

### 6.9 Policy evaluation (`adlc.policy`)

1. Compile CEL once (cache). 2. Resolve referenced paths through the evidence provider (layered: real sources, then
synthetic files labelled `synthetic`). 3. Run predicates. 4. Anything but `true` = not passed with a reason; errors,
>1 s, >10,000 rows, >100,000 characters fail closed. 5. Approval conditions that cannot be evaluated require the
approval; follow-on conditions that cannot be evaluated do not fire. 6. One `policy_decision` row per call.

Evidence sources: `T<n>` (latest closed run: status, signers, waivers, `bound_to`, artifacts, emitted values),
`run`, `intake`, `trigger`, `timeline`, `tier`, `waivers` (approved waivers of the use case), `param`, `directory`,
tool evidence, synthetic.

### 6.10 Parameter resolution (`policy/parameters.resolve`)

For each guardrail: tier value (tier = use case tier or `medium`); a profile value is used only when within the
guardrail (`max`: ≤, `min`: ≥, `superset`: contains all); otherwise rejected with a reason. Result frozen in
`run_parameter_set` at run open.

### 6.11 Agent build (`agents/runner.py`)

1. Context pack: registered prompt and playbooks (hash-checked), use case, trigger, previous artifacts,
   clarifications, failed controls, prerequisite evidence; untrusted text in `<data>` blocks; `context_hash`.
2. Bounded loop per tier limits (`ADLC_AGENT_LIMITS`, overrides): model call → tool calls → … → output.
3. Gateway (`RoutingGateway`): walk the tier's models for `ADLC_MODEL_PROFILE`; skip no key / data class below the
   run's ceiling / context too large; fall back only on outages; refusal, truncation or request error ⇒ correction
   (`ADLC_AGENT_CORRECTIONS`) then attempt failed; nothing answered ⇒ `unavailable` (outage limit
   `ADLC_MODEL_OUTAGE_LIMIT`) or `request_error`. One `model_call` row per request.
4. Tools: `ToolGate.call` ⇒ `policy.authorize(agent:<run_id>, action, resource)` ⇒ knowledge (`KnowledgeTool`) or
   acting tool (`McpTool` with a run token). Every call ⇒ `tool_call` (+ `tool_result` for evidence).
5. Output validation against the spec's artifact shapes; citations recorded; one `agent_attempt` row.
6. Cost alerts at `ADLC_COST_ALERT_LEVELS` (`cost_alert`).

Reviewer: same runtime; independent input (no builder reasoning); scores each checklist item; returns status, scores,
findings, reason, root cause. `ADLC_REVIEWER_MODE` selects `model` (the model reviewer) or `stub` (default; a scripted reviewer).

### 6.12 Edit and re-check (`LedgerService`)

`artifact_edited`: new `artifact_version` (producer = person), approvals stop counting
(`approvals_after_sign_off_id`), pending waiver withdrawn, `controls_pending = true` at sign-off, version + 1. The
worker re-runs controls (`controls_rechecked`). Uploads: spreadsheet rows (`spreadsheet.py`) or attachments
(`FileStore`, size and type checks, Office macros refused, download only).

---

## 7. External interfaces

### 7.1 HTTP API (`adlc.api`)

31 operations; full contracts in `docs/api-reference.md` (generated from OpenAPI by `make api-docs`).

| Area | Operations |
|---|---|
| Health, sessions | `GET /health`, `POST /auth/sign-in`, `POST /auth/sign-out`, `GET /auth/me` |
| Use cases | `POST /usecases`, `GET /usecases`, `GET /usecases/{id}`, `POST /usecases/{id}/verify` |
| Inbox, runs | `GET /inbox`, `GET /runs/{run_id}`, `POST /runs/{run_id}/decisions`, `POST /runs/{run_id}/escalation` |
| Artifacts | `PUT …/artifacts/{artifact_id}`, `POST …/spreadsheet`, `POST …/attachments`, `GET …/history`, `GET /runs/{run_id}/attachments/{content_hash}` |
| Requests | `POST /clarifications/{id}/answers`, `POST /waivers/{id}/decision`, `GET /dead-letters`, `GET /dead-letters/{event_id}`, `POST /dead-letters/{event_id}/requeue` |
| Changes, events | `GET /changes`, `POST /changes/{id}/decision`, `GET /events/proposed`, `POST /events/proposed/{usecase}/{terminal}/{run_number}/{event_id}` |
| Dashboard | `GET /dashboard/usecases/{id}/journey`, `…/kpis`, `GET /dashboard/portfolio`, `GET /dashboard/activity`, `GET /dashboard/runs/{run_id}/timeline` |

Conventions: run ids contain `/`; every changing operation on a run sends `expected_version`; the actor is always
the signed-in person; responses are Pydantic `ApiModel`s (`extra="forbid"`); a golden-shape test pins the JSON;
`web/src/api/schema.d.ts` is generated from the same OpenAPI document (freshness test).

**Error mapping** (`api/errors.py`), body `{"kind", "detail" (≤500 chars), "field"?}`:

| Exception | Status | kind |
|---|---|---|
| no or invalid session | 401 | `not_signed_in` |
| `NotAuthorised`, CSRF failure | 403 | `not_allowed` |
| `NotFound`, `UnknownRun`, `UnknownEvent`, `NotDeadLettered` | 404 | `not_found` |
| `StaleRun` | 409 | `stale` |
| `InvalidTransition`, `AlreadyAnswered`, `NoActiveSpecs` | 409 | `wrong_state` |
| `Invalid`, `InvalidDecision`, `InvalidUpload`, `AttachmentRefused`, `UnknownArtifact`, request validation | 422 | `invalid` |

### 7.2 Events

Catalogue (only these are accepted): `usecase.submitted`, `Tn.pass`, `Tn.exception`, `Tn.rework.<root_cause>`,
`Tn.escalate`, `Tn.terminate`, `T7.rollback`, `T8.event.<type>`, `T9.reentry.Tn`, `change.requested`,
`lifecycle.review_due`. Envelope: `event_id`, `event_type`, `usecase_id`, `correlation_id`, `causation_run_id`,
`payload` (run id, status, root cause, comment, decision fields, target/re-entry terminal, waiver id, emits, notify,
ledger key).

### 7.3 MCP servers

| Server process | Auth | Tools |
|---|---|---|
| `adlc-knowledge` | Bearer `ADLC_KNOWLEDGE_TOKEN` | Per source (`/mcp/<source>/`): `search`, `read`; data-class filter; caps |
| `adlc-tools`, `adlc-pilot-bridge` | Run token (below) | Per `tools/catalogue.py`: server, name, scope, model-settable arguments, bound values, evidence kind, time limit |

**Run token** (`tools/token.py`): claims `{run_id, usecase_id, terminal_id, attempt, scopes, bound, iat, exp}`;
`<version>.<base64url(canonical JSON)>.<HMAC-SHA256(ADLC_TOOLS_TOKEN_KEY)>`; 5 minutes. The server verifies the
signature, expiry, the tool's scope and the required bound values before the handler runs.

---

## 8. Security design

| Concern | Design |
|---|---|
| Authentication | `LocalIdentityProvider`: accounts in `ADLC_ACCOUNTS_FILE` (outside the repo), scrypt `scrypt$n$r$p$salt$hash`; placeholders never sign in (in `demo` they stop start-up). Sessions: itsdangerous-signed tokens, `ADLC_SESSION_TTL`; sign-out revocations in memory (lost on API restart: accepted MVP limit) |
| Browser session | Cookie mode: `adlc_session` HttpOnly, SameSite=Strict, Path=/, Secure on https. CSRF = `base64url(HMAC-SHA256(session_secret, "csrf\0"+token))`, returned by sign-in and `/auth/me`; required in `X-ADLC-CSRF` for non-GET/HEAD/OPTIONS cookie requests; cookie sign-in needs `X-ADLC-CSRF: sign-in`. Bearer wins when both present. Page scripts never see the token |
| Endpoint protection | `install_auth` middleware: every path needs a session except `PUBLIC_PATHS = {"/health", "/auth/sign-in"}` |
| Authorization (people) | Roles from the pinned spec and `roles.yaml` via `inbox/rules.py`, shared by Inbox and operations: sign-off roles and `plus` roles, terminate `set_by`, waiver approvers (≠ proposer), clarification addressee, accountable roles, editors, CoE |
| Authorization (agents) | `policy.authorize`: run scope → tool scopes → deny → allow → default deny; duty groups (V-16) |
| Tools | Run tokens with scopes and bound package hashes (candidate from T3, authorised from T6) |
| Web | `adlc-web`: strict CSP, no CORS, security headers, immutable asset caching, a cookie jar that stores nothing (no cross-user cookie leak), logs method/path/status only |
| Rendering | Agent and person text rendered as text only (`dangerouslySetInnerHTML` banned by lint); attachments download only |
| Secrets | Environment only; logging filter drops credential-like attributes; model keys never logged or traced |
| Integrity | Triggers + hash chain (section 4.3, 6.6) |

---

## 9. Concurrency and resilience

- API: thread pool (sync endpoints); reads concurrent (WAL); writes serialised by `BEGIN IMMEDIATE`, waiting up to
  `ADLC_DB_BUSY_TIMEOUT`; stale protection by `expected_version`.
- Worker: one process, rounds never overlap; steps one at a time (no parallel runs). Safe with two workers except
  monitors (duplicate events possible). Details and open options: `docs/codebase-flow.md` section 9.
- Crash safety: one transaction per signal; transactional outbox; leases expire into automatic retries; outbox
  retries and dead letters; timers persisted.
- Model resilience: ordered fallback on outages only; a `model_unavailable` result is deferred and retried (`model_unavailable_since`; an expired lease then is not an interrupted step); escalation
  after the outage limit.
- Resilience checks: `make resilience` (restart mid-run, duplicate delivery, dead letter; `ADLC_ROUTE_FAULT`).

---

## 10. Configuration

All settings are environment variables with prefix `ADLC_` (`.env`, see `.env.example`; `deploy/local.env` for
localhost values). Validated at start-up; a missing or invalid value stops the process with the setting's name.

| Group | Settings |
|---|---|
| Common | `ENV` (dev/demo), `DB_PATH`, `DB_CONNECT_TIMEOUT`, `DB_BUSY_TIMEOUT`, `LOG_LEVEL`, `OTLP_ENDPOINT` |
| Identity | `SESSION_SECRET`, `SESSION_TTL`, `ACCOUNTS_FILE`, `ROLE_CATALOGUE` |
| Orchestrator | `TIME_SCALE`, `POLL_INTERVAL`, `LEASE`, `HEARTBEAT_MAX_AGE`, `MONITOR_INTERVAL`, `ROUTE_FAULT` (tests), `DEADLETTER_ROLE`, `SYNTHETIC_DIR`, `SPEC_DIR` |
| Files | `FILE_STORE_DIR`, `ATTACHMENT_MAX`, `ATTACHMENT_TYPES` |
| Agents | `MODEL_PROFILE`, `REVIEWER_MODE`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `AGENT_CORRECTIONS`, `MODEL_OUTAGE_LIMIT`, `COST_ALERT_LEVELS`, `AGENT_LIMITS`, `AGENT_LIMIT_OVERRIDES` |
| Knowledge | `KNOWLEDGE_URL`, `KNOWLEDGE_TOKEN`, `KNOWLEDGE_DIR`, `KNOWLEDGE_PORT`, `KNOWLEDGE_ALLOWED_HOSTS` |
| Tools | `TOOLS_URL`, `PILOT_BRIDGE_URL`, `TOOLS_TOKEN_KEY`, `TOOLS_TIMEOUT_S`, `TOOLS_PORT`, `TOOLS_ALLOWED_HOSTS`, `CONTROLS_FILE` |
| Bridge | `BRIDGE_PORT`, `BRIDGE_ALLOWED_HOSTS`, `BRIDGE_DATA_DIR`, `BRIDGE_PILOT_{DEV,TEST,PRODSIM,LAB,TRAFFIC}_URL`, `BRIDGE_PHOENIX_URL`, `BRIDGE_PILOT_SERVICE`, `BRIDGE_MONITOR_INTERVAL_S`, `REDTEAM_SUITE` |
| API, web | `API_PORT`, `API_URL`, `UI_PORT`, `UI_DIST_DIR`, `LEGACY_UI_PORT`, `UI_DASHBOARD_REFRESH`, `PHOENIX_UI_PORT` |

Spec-side configuration (not environment): `adlc-specs/terminals/*.yaml` and `adlc-specs/shared/*.yaml` (roles,
guardrails, metrics, mcp_servers, model_catalogue, model_tiers, agents, permissions, predicates, events,
evidence_sources, data_classes, risk_tiers, root_causes, route_destinations, change_classes).

---

## 11. Observability

| Signal | Design |
|---|---|
| Traces | OpenTelemetry per process, OTLP/HTTP to Phoenix; spans `adlc.policy.<evaluate|authorize>`, `agent.build`, `reviewer.review`, `adlc.model.call` (no content), tool calls, ledger operations; attributes `run_id`, `usecase_id`, `terminal_id` from an allow list; `/health` not traced; headers never captured |
| Logs | stdlib logging to stderr; credential filter; `auth.sign_in account_name outcome`; web proxy logs method, path, status |
| Records | `run_transition`, `run_activity`, `policy_decision`, `model_call`, `agent_attempt`, `tool_call`, `knowledge_retrieval`, `cost_alert` (queryable evidence, shown on Journey, Activity and run timeline) |
| Health | `/health` on API, web, knowledge, tools, bridge; `adlc-orchestrator health` (heartbeat age ≤ `HEARTBEAT_MAX_AGE`) |
| Trace of a use case | `make trace USECASE=UC-0001` / `adlc-ledger trace` |

---

## 12. Web application (`web/`, feature 022)

| Aspect | Design |
|---|---|
| Stack | React 19, TypeScript 5.9, Vite 8, React Router 8, TanStack Query 5, AG Grid Community 36, Plotly.js (basic dist), openapi-fetch; pnpm via corepack; Node at build time only |
| Serving | `adlc-web` (Starlette): `/assets` (immutable cache), top-level build files, SPA fallback to `index.html`, `/config.json`, `/health`, `/api/*` proxied unchanged to `ADLC_API_URL` with header allow lists |
| API client | `src/api/client.ts` is the only code that calls `fetch` (lint rule); types from `schema.d.ts`; errors mapped to `ErrorBody`; CSRF header added on changing requests |
| Session | `src/auth/session-context`: `/auth/me` at start (race-guarded), sign-in in cookie mode, sign-out; `require-session` guard with `next` redirect |
| Navigation | One registry table (`src/nav/registry`) drives routes and sidebar (pages lazy-loaded) |
| Pages | Sign-in, Inbox (30 s refresh), New use case, Use cases, Run (summary bar, artifacts beside recommendation, control results, decision form, evidence tabs, artifact grid editable ≤1,000 rows else read-only + upload, attachments download only), Clarification, Escalation, Waiver, Dead letters (CoE), Journey, Activity, Portfolio |
| Rules | Statuses shown as platform words; every action sends the run version; stale answer reloads the run; text never rendered as HTML |
| Tests | Vitest + RTL + MSW (fixtures from API goldens), Playwright e2e against `tests/e2e/stack.py` (seeded, stub agents) in Chromium/Firefox/WebKit, axe accessibility, console/CSP guard |

---

## 13. Testing strategy

| Level | Location | Covers |
|---|---|---|
| Unit | `tests/unit/` | Pure modules (states with Hypothesis properties, routing, predicates, parameters, tokens), boundaries, no hard-coded values, build contract, OpenAPI/API docs freshness |
| Integration | `tests/integration/` | Engine with a real SQLite template database per test, API (response goldens, cookie session, CSRF), web server, ledger, tools, demo auto run |
| Spec | `make spec-validate` | All rules L1–L5 over `adlc-specs/` |
| Web | `make web-check` (lint, typecheck, Vitest), `make web-e2e` (Playwright) | |
| End to end | `make demo-auto` / `make demo-local-auto`, `make resilience` | Full lifecycle with rehearsed replies |
| CI | `make check` on every push | |

---

## 14. Known limits and open items

| Item | Reference |
|---|---|
| Worker runs steps one at a time; monitors not safe with two workers | `docs/codebase-flow.md` §9 |
| Exception emits no values (T0 tier falls back to medium); waiver `recheck_at` unused; only expiry re-checked; no prerequisite look-ahead | `docs/exception-outcome.md` |
| Metric names: playbook and `metrics.yaml` differ; threshold metric names not checked against the catalogue | metrics catalogue discussion |
| Session revocations in memory (lost on API restart) | `adlc.identity` |
| SQLite: single writer; triggers can be dropped by a process with file access (chain still detects changes) | section 4.3 |
| Synthetic evidence sources until real integrations exist | `adlc.policy` README |
| 022 cutover (remove Streamlit) pending | `specs/022-react-web-app/tasks.md` T069–T078 |
