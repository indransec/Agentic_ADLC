# Agentic ADLC: User Manual (Phase 2 Option A, the board)

**Product as built**: Phase 2 Option A (features 015–020) on top of the Phase 1 MVP. People work
on an **ADO-style board** (the built-in Azure DevOps simulator): they create use cases, make every
decision, answer clarifications and approve change requests there. The platform's web application
becomes the **operations console** for the evidence, the dashboards and the sync. The platform
stays the only source of truth: the board is how people see and steer it.

**Who this is for**: the people who decide (business owners, product owners, architects, leads,
officers, release managers), the ADLC CoE who operates the platform and the board sync, and
whoever installs it or presents the demo.

---

## 1. What the product does

The platform takes an agentic use case from idea to production and on to retirement through ten
lifecycle **terminals**, T0 to T9. At each terminal, **agents build and people decide**:

1. A builder agent produces the terminal's artifacts.
2. The platform runs the terminal's **controls** on them.
3. A reviewer agent **recommends** an outcome.
4. The people who hold the terminal's sign-off roles **decide** (pass, rework, exception,
   terminate), now on the board.

Every decision is written to an append-only, hash-chained **evidence ledger** with the spec
version, the person (and, for board decisions, the board item and update it came from) and the
evidence hashes.

### How the pieces fit

| Piece | Who uses it | What for |
| --- | --- | --- |
| **The board** (ADO simulator, port 8600) | everyone who decides | the Epic board, the backlog, work item forms: create, decide, answer, comment |
| **The platform** | nobody directly | runs the lifecycle, agents, controls, policy and the ledger |
| **The board sync** (`board` process) | nobody directly; the CoE watches it | writes the platform's state onto the board; turns people's board changes into platform decisions |
| **The operations console** (web app, port 8501) | everyone, for evidence and dashboards; the CoE for operations | run evidence and artifact editing, Journey, Activity, Portfolio, Dead letters, Sync status |

## 2. Key ideas

| Term | Meaning |
| --- | --- |
| **Use case** | One agentic product taken through the lifecycle (`UC-0001`). On the board: an **Epic**. |
| **Terminal** | One lifecycle stage, T0 to T9. On the board: the Epic's **column**. |
| **Run** | One pass through a terminal (`UC-0001/T1/run-2`). On the board: a **Feature** under the Epic. |
| **Clarification** | A question an agent asks a role. On the board: a **Task** under the run's Feature. |
| **Change request** | A release's ITSM change. On the board: a **Change Request** under the run's Feature. |
| **Sub-stage** | Where the current run is (Building, Reviewing, Awaiting sign-off, Escalated…), shown on the Epic's card. |
| **Artifact, control, recommendation** | What the agent built, the checks on it, the reviewer's advice: shown in the console, linked from each run item. |
| **Decision field** | The one field on a run (or change request) item where a person records a decision. |
| **Risk tier** | Low, medium or high, set when T0 passes. |

### The terminals and who signs them off

| Terminal (board column) | Question | Sign-off |
| --- | --- | --- |
| T0 Intake & Qualification | Should we do this at all? | business owner |
| T1 Requirements & Outcome | What exactly must the agent achieve? | product owner and business owner |
| T2 Architecture & Design | How should the agent operate? | solution architect and security officer |
| T3 Build & Integration | Can we construct it reproducibly? | engineering lead |
| T4 Evaluation | Does it behave as designed? | QA and evaluation lead and product owner |
| T5 Trust, Risk & Assurance | Is it safe and compliant for release? | by risk tier: low, security; medium, security and privacy; high, security, privacy, RAI and compliance (plus the RAI board) |
| T6 Release Readiness | Is everything ready for production? | release manager, service owner, business owner |
| T7 Deployment & Transition | Can it be deployed and handed over? | release manager and service owner |
| T8 Operate & Observe | Is it operating as expected? | service owner |
| T9 Evolve / Retire | Improve it or retire it? | evolve: product owner; retire: business, service and data owners |

Each run item's description says who it is **waiting for**, so you never need this table to act.
After the last column come **Closed** and **Removed** (terminated).

### Roles and board users

Platform roles come from `adlc-specs/shared/roles.yaml` (business owner, product owner, solution
architect, engineering lead, QA and evaluation lead, security, privacy, RAI and compliance
officers, risk owner, release manager, service owner, SRE, data owner, ADLC CoE). On the board,
each person has a board user; the accounts file maps the two (`board_identity`). In the demo the
board users are `business.owner@adlc.demo`, `product.owner@adlc.demo` and so on. The board's
service account (`adlc-platform@adlc.demo`) is the platform itself: it never signs in to the pages.

### The decisions

| Decision value | When | What it needs |
| --- | --- | --- |
| **Pass** | the artifacts are good enough | the values the pass must record (for example `risk_tier`); a reason if you disagree with a "rework" recommendation |
| **Rework** | something must be redone | a comment and a **root cause** (requirement, design, architecture, implementation, control missing, missing evidence, ops gap, defect, readiness gap, environment, qualification); a reason if you disagree with a "pass" recommendation; sometimes a rework target |
| **Exception** | accept a gap for now | the waiver values the terminal asks for (owner, expiry, compensating control) |
| **Terminate** | stop the use case | a comment or a reason |
| **Approve waiver** / **Reject waiver** | a waiver approver (another person) decides a pending waiver | a comment |
| **Complete escalation** | the accountable role resolved an escalated run | a comment |
| **Approve change** / **Reject change** | on a Change Request item, the ITSM owner (release manager) | a comment |

## 3. Installing and starting

Everything from the Phase 1 manual applies (uv, git, make; `.env` from `.env.example`; an
accounts file outside the repository with hashed passwords; a model provider key). For the board:

1. **Give each person a board user** in the accounts file:

   ```yaml
   - account_name: owner.business
     display_name: Business Owner
     roles: [business_owner]
     credential_hash: '<from uv run adlc-account hash>'
     board_identity: business.owner@adlc.demo
   ```

2. **Issue the sync's token** in the simulator and put it in `.env`:

   ```bash
   docker compose -f deploy/compose.yaml --env-file .env exec ado-sim \
     ado-sim token issue adlc-platform@adlc.demo
   # .env: ADLC_BOARD_ENABLED=true and ADLC_BOARD_TOKEN=<that token>
   ```

   Without Docker: `cd ado_sim && ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db uv run
   ado-sim token issue adlc-platform@adlc.demo`.

3. **Let people sign in to the board**: either set `ADO_SIM_DEMO_PASSWORD` (one shared password
   for every demo user, off by default) or give each a page password
   (`ado-sim password set --all`). People may also sign in with a personal access token.

4. **Start**: `make up` (or `make local`), then check the mapping:
   `adlc-board check-mapping` should say the tracker mapping fits the board.

| What | Address |
| --- | --- |
| The board | `http://localhost:8600` |
| The operations console | `http://localhost:8501` |
| Traces (Phoenix) | `http://localhost:6006` |
| Platform API | `http://localhost:8000` |

`ADLC_BOARD_PUBLIC_URL` is the board's address for browsers (default `http://localhost:8600`
under Docker); the console uses it for links to work items.

The board defaults (organisation `adlc-demo`, project `Agentic ADLC`, area
`Agentic ADLC\Use cases`) come from `.env` and `adlc-specs/tracker_mapping.yaml`.

## 4. Working on the board

### Signing in

Open `http://localhost:8600`. Choose your user and give your page password, the shared demo
password, or a personal access token. A session lasts up to 8 hours; **Sign out** ends it. Every
change you make on the pages is recorded as yours, exactly as through the API.

The navigation bar has **Board** and **Backlog**.

### The board

One column per terminal (T0 to T9, then Closed and Removed, collapsed). Each card is a use case's
Epic, showing its **sub-stage**. The board refreshes itself every few seconds; filter by area
path at the top. **Cards cannot be dragged**: the columns belong to the platform.

### Creating a use case (T0)

On the board, **New Epic**: a title (the use case's name) and a description (the intake: what the
agent should do, for whom, the data involved, the expected benefit; at least a few sentences).
**Choose the area `Agentic ADLC\Use cases`**: only Epics in that area become use cases. Within a
poll interval (about 10 seconds) the platform registers it: the Epic gets its use case id and
sub-stage, and a T0 run item appears beneath it.

### The backlog

**Backlog** shows each Epic with its runs (Features) and their clarifications and change requests
beneath, as a tree you can collapse level by level; it refreshes like the board. Every row opens
its work item form.

### The work item form

Opening an item shows its fields in sections (for a run: **Decision** first, then **Run**), the
parent and children, the **comments** (newest first; the platform's replies are signed
"ADLC: …") and the **history** (who changed which field, from what to what).

A run item's description tells you everything you need to decide:

- its state, and **who it is waiting for**;
- the decision values you may choose, and what each one needs;
- the root causes, which root causes need a rework target, and the values a pass must give;
- the reviewer's recommendation;
- who has already approved, and any pending waiver.

The **ADLC Evidence Link** opens the run's evidence in the console (section 5). Read it before you
decide: the board shows what to decide, the console shows what it rests on.

### Making a decision

On the run item's form:

1. **ADLC Decision**: choose the value from the list.
2. **ADLC Comment**: your comment.
3. The inputs the description asks for, either in their own fields (**ADLC Root Cause**,
   **ADLC Reason**, **ADLC Rework Target**, **ADLC Values**) or as lines in the comment:

   ```text
   The KPI baselines are estimates; take them from the ticket system's last quarter.
   root cause: requirement
   reason: The baselines must be measured before we commit to targets.
   ```

   **ADLC Values** holds one `name: value` per line (for example `risk_tier: medium`); in a comment,
   write `value risk_tier: medium`. A field wins over a comment line that says otherwise.
4. **Save**.

Within about 10 seconds the platform answers with a comment on the item:

- **accepted**: the decision is recorded as yours, the decision field and its inputs are cleared
  for the next approver, and the item and its Epic move on;
- **refused** with the reason (for example "Rework needs: comment, root cause", "the reviewer
  recommended pass; a reason is required", "not authorised", "the run has moved on"): the
  decision field is cleared, your comment and inputs stay so you can complete them and decide
  again.

If two people save the same item at once, the second gets a **conflict**: the form shows the
current item with your changes kept; check them and save again.

### Answering a clarification

When an agent needs information, a **Task** appears under the run with the numbered questions and
the role they are for. That person opens it and types the answers, one numbered line per
question, in **ADLC Clarification Answer**:

```text
1. Incident records are kept for 24 months, then anonymised.
2. EU only.
```

Save. The platform accepts them, the task closes, and the same run continues (not a rework).

### Escalations and waivers

- **Escalated** run (too many reworks, or late): the accountable role resolves the issue and
  sets **Complete escalation** on the run item.
- **Exception**: the approver sets **Exception** with the waiver values; a different person with
  a waiver approver role (for example the risk owner) then sets **Approve waiver** or **Reject
  waiver** on the same run item.

### Approving a change request

At release, an agent raises an ITSM change. A **Change Request** item appears under the run with
its summary, risk and window, and who decides it. The release manager sets **Approve change** (or
**Reject change**) with a comment. The platform records it, the item shows Approved, and the
waiting run re-runs its checks. Another role's decision, or a second decision, is refused with a
comment.

### What you cannot change (and what happens if you try)

The platform owns the columns and its own fields: an Epic's state, sub-stage and use case id; a
run's title, description, state, id and evidence link; the same on clarifications and change
requests. You can still change them on a form, as in real ADO, but the platform **sets them back
within a poll interval and says why** in a comment. Your own fields (decision, comment, inputs,
answers, tags) are yours.

Board items people add themselves (a User Story or Task as a personal checklist) are left alone:
the platform does not read them, and the agents never see them. To tell an agent something, use a
rework comment or a clarification answer.

## 5. The operations console

With the board sync on, the web application is the **operations console**. Sign in with your
platform account. The sidebar shows **Use cases** (the start page), **Journey**, **Activity**,
**Portfolio**, **Dead letters**, and for the CoE **Sync status**.

### Run evidence

Following a run item's evidence link opens the run in the console, after sign-in. You see:

- the artifacts, with the agent's and people's versions;
- the reviewer's recommendation and findings, and the control results;
- prerequisites with their results and reasons, citations, prior rework, clarifications,
  approvals, the waiver, activity, timeline and evidence hashes.

While the run awaits **your** sign-off you may still correct an artifact here; the controls run
again.

Where the inbox had the decision form, the console says **the decision is made on the board** and
links to the run's item (**Decide on the board**).

### Pages that moved to the board

Inbox, New use case, Clarification, Escalation and Waiver are still at their old addresses, but
say the action is now made on the board, with a link to it.

### Dashboards

**Journey** (lanes per terminal, runs, rework and reroute arrows, KPIs), **Activity** (agents' and
people's actions, filterable) and **Portfolio** (KPIs across use cases) work as before.
**Use cases** offers **Verify the ledger for this use case**.

### Sync status (CoE)

The board sync's health, refreshed regularly:

| Shown | Meaning |
| --- | --- |
| Last poll | `ok`, or why not (`board_unreachable`, `auth_failed`, `mapping_invalid`) |
| Inbound watermark age | how far behind the board the platform's reading is |
| Outbound pending / Oldest pending | platform changes not yet written to the board |
| Reverted board changes | people's changes to platform-owned fields that were set back |
| Refused board changes | by reason |
| Board deliveries dead-lettered | use cases whose board writes failed after their retries, each with **Re-queue** (these are board deliveries; platform events are on Dead letters) |
| Reconciliation | the last one's differences; **Reconcile now** behind a confirmation |

**Reconcile now** compares every board item with the platform and corrects the board (only the
platform's own fields; a person's unread decision is left alone), listing every difference.

## 6. Operating the board sync

| Task | How |
| --- | --- |
| Check the mapping fits the board | `adlc-board check-mapping` |
| Sync health | console, Sync status; or `adlc-board health` |
| Correct drift | console, Reconcile now; or `adlc-board reconcile --as <coe account>` |
| Re-queue a board delivery | console, Sync status; or `adlc-board requeue <UC-nnnn> --as <coe account>` |
| Fall back to the inbox | `ADLC_BOARD_ENABLED=false` in `.env`, restart the API (`make up`): within a minute the web app is the inbox again and people decide there |
| Board data | the `ado-sim` volume; `ado-sim reset --yes` reseeds (removes items and tokens) |

Everything else (health, traces, ledger verification and trace, backups, specs, accounts) is as in
the Phase 1 manual.

## 7. Running the demo on the board

The SA §21 demo, decided on the board: D-1 to D-9, plus **D-12** (the product owner drags the
Epic to T5; the platform sets it back with a comment) and **D-13** (the board drifts out of step;
the CoE reconciles from the console).

```bash
# .env (demo environment): ADLC_ENV=demo, ADLC_BOARD_ENABLED=true,
#   ADLC_BOARD_TOKEN=<40+ characters>, ADO_SIM_DEMO_PASSWORD=<12+ characters>,
#   ADLC_DEMO_BOARD_TOKENS=<a path outside the repository>
make demo-reset      # platform, pilot and board; registers the sync's and the demo people's tokens
make demo-auto       # rehearsal: the driver acts on the board as each demo person
make demo            # presenter: the driver names the board user, the item address and every value
make demo FROM_STEP=10
```

Keep the board and the console's **Journey** side by side. At each human step the driver prints
who to sign in as on the board, the item to open, and the values to set; it continues once the
platform has read the change. The step-by-step guide is `demo/README.md`. The tokens file is a
secret (readable by you only): never commit or print it.

With the board sync off, the demo is the Phase 1 demo in the inbox (steps 16 and 17, the board
moments, are skipped).

## 8. Limits and troubleshooting

- The board is the built-in ADO simulator: Epics, Features, Tasks and Change Requests, no drag and
  drop, comments shown as plain text, a token import only the simulator has. Its differences from
  real Azure DevOps are listed in `ado_sim/contract/differences.md`.
- The sync polls the board (every 10 seconds by default), so a board change takes up to that long
  to be acted on.
- The **New Epic** form defaults to the area you filtered by, or the first one (`Agentic ADLC`):
  choose `Agentic ADLC\Use cases`, or the Epic is not registered and nothing tells you.
- If a board update fails unexpectedly inside the sync (rather than being refused), it is not
  answered until the board process restarts; other items carry on.
- The Phase 1 limits still apply (ledger bypass detectable, not prevented; sessions not revoked
  across restarts; plain HTTP on one host).

| Symptom | Likely cause |
| --- | --- |
| A new Epic never gets a use case id | it is not in `Agentic ADLC\Use cases`, or its description is empty |
| A decision is "refused" | read the comment: a missing input, the wrong role, or the run moved on |
| My change to the Epic's column was undone | columns belong to the platform; decide on the run item instead |
| "not a mapped platform user" | your board user is not any account's `board_identity` |
| Sync status shows `board_unreachable` | the simulator is down; changes are kept and delivered when it is back |
| The console shows the inbox | the board sync is off (`ADLC_BOARD_ENABLED`), or the API was not restarted after turning it on |
