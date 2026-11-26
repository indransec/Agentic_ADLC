# Agentic ADLC: User Manual

**Product as built**: the Phase 1 MVP (features 001–014) on SQLite and Arize Phoenix, with or
without Docker (branch `feature/sqlite`). People work in the platform's own web application (the
inbox). For the board-driven product of Phase 2 Option A, see that branch's manual.

**Who this is for**: the people who decide (business owners, product owners, architects, leads,
officers, release managers), the ADLC CoE who operates the platform, and whoever installs it or
presents the demo.

---

## 1. What the product does

The platform takes an agentic use case from idea to production and on to retirement through ten
lifecycle **terminals**, T0 to T9. At each terminal, **agents build and people decide**:

1. A builder agent produces the terminal's artifacts (requirements, a design, a build, an
   evaluation report and so on).
2. The platform runs the terminal's **controls** (checks written in the terminal's spec) on them.
3. A reviewer agent reads the artifacts and the control results and **recommends** an outcome.
4. The people who hold the terminal's sign-off roles **decide**: pass, rework, exception or
   terminate. Nothing moves to the next terminal without that human decision.

Every decision is written to an append-only, hash-chained **evidence ledger** with the spec version,
the person, the evidence and its hashes, so the whole lifecycle can be traced and verified later.

What you see as a user: an inbox of things waiting for you, a page per run with the evidence and the
decision form, and dashboards of how every use case is progressing.

## 2. Key ideas

| Term | Meaning |
| --- | --- |
| **Use case** | One agentic product being taken through the lifecycle (for example Incident Triage). It has an id such as `UC-0001`. |
| **Terminal** | One lifecycle stage, T0 to T9 (table below). Each is defined by a spec in `adlc-specs/terminals/`. |
| **Run** | One pass through a terminal for a use case (`UC-0001/T1/run-2` is the second T1 run). A rework opens a new run. |
| **Artifact** | Something a terminal produces: a table, a document, a file. Built by the agent; people can correct it before signing off. |
| **Control** | A check on the terminal's own artifacts (completeness, thresholds, policy rules), run before anyone can sign off. Blocking controls must pass, or be covered by an exception. |
| **Prerequisite** | A check made when a terminal opens: the previous terminal ended with pass or exception, the evidence it handed forward exists, and environments and versions are as expected. An unmet one leaves the run **blocked**. |
| **Emitted values** | What a terminal hands forward when it closes with pass or exception (for example T0's risk tier, T1's thresholds, T3's package hash). They are recorded in the ledger and the use case's profile, and later terminals check against them. |
| **Reviewer recommendation** | The reviewer agent's view (pass or rework, with findings). People may disagree, with a reason. |
| **Sign-off** | Passing a run. Some terminals need two or more approvers from different roles. |
| **Risk tier** | Low, medium or high, set when T0 closes (pass or exception). It changes some sign-off rules, durations and assurance depth. |
| **Ledger** | The tamper-evident record of every decision and its evidence. |

### The terminals and who signs them off

| Terminal | Question it answers | Accountable role | Sign-off |
| --- | --- | --- | --- |
| T0 Intake & Qualification | Should we do this at all? | business owner | business owner |
| T1 Requirements & Outcome | What exactly must the agent achieve? | product owner | product owner and business owner |
| T2 Architecture & Design | How should the agent operate? | solution architect | solution architect and security officer |
| T3 Build & Integration | Can we construct the agent reproducibly? | engineering lead | engineering lead |
| T4 Evaluation | Does the agent behave as designed? | QA and evaluation lead | QA and evaluation lead and product owner |
| T5 Trust, Risk & Assurance | Is it safe and compliant for release? | security officer | by risk tier: low, security; medium, security and privacy; high, security, privacy, RAI and compliance (plus the RAI board) |
| T6 Release Readiness | Is everything ready for production? | release manager | release manager, service owner, business owner |
| T7 Deployment & Transition | Can it be deployed and handed over safely? | release manager | release manager and service owner |
| T8 Operate & Observe | Is it operating as expected? | service owner | service owner |
| T9 Evolve / Retire | Improve it or retire it? | product owner | evolve: product owner; retire: business owner, service owner and data owner |

The exact rules live in each terminal's spec (`authorities.sign_off`); the form on the run page
always shows what is still needed.

### Roles

Every person signs in with an account that holds one or more roles from
`adlc-specs/shared/roles.yaml`: business owner, product owner, solution architect, engineering
lead, QA and evaluation lead, security officer, privacy officer, responsible AI (RAI) officer,
compliance officer, risk owner, release manager, service owner, SRE, data owner, and the ADLC CoE
(who handles dead letters and other platform operations). The platform checks every action against
the person's roles; the web app only hides actions you cannot take.

### A run's states

| State | What it means for you |
| --- | --- |
| opened, building, checking, reviewing | The platform and agents are working. Nothing to do. |
| awaiting clarification | The agent asked a question; the addressed role must answer. |
| awaiting sign-off | The run waits for a decision from its approvers. |
| blocked | Something the run needs is missing (a prerequisite, a change approval); the page says what. |
| escalated | Too many reworks (more than the spec's limit, usually 3) or the run took too long: an accountable person must resolve it. |
| closed | Decided. The final status is pass, rework, exception or terminated. |

### The decisions

| Decision | When | What you must give |
| --- | --- | --- |
| **Pass** | The artifacts are good enough. | Any values the pass must record (for example the risk tier at T0). A reason if you disagree with a "rework" recommendation. |
| **Rework** | Something must be redone. | A comment, and a **root cause** (requirement, design, architecture, implementation, control missing, missing evidence, ops gap, defect, readiness gap, environment, qualification). The root cause decides where the rework goes: for example an implementation defect found at T4 goes back to T3. A reason if you disagree with a "pass" recommendation. |
| **Exception** | A gap is accepted for now. | The waiver details the terminal asks for (owner, expiry, compensating control), and the same values a pass would record (for example the risk tier at T0). A waiver approver (another person) must approve it; T6 checks waivers again. |
| **Terminate** | The use case should stop. | A comment or a reason. |

**Why both controls and prerequisites?** Controls decide whether a terminal's own work is good
enough to leave; the next terminal's prerequisites decide whether it may start. A prerequisite does
not repeat the earlier controls: it checks that the earlier terminal ended with pass or exception and
handed forward what is needed, plus anything that can change in between (such as which build is
deployed in the test environment). A terminal can also open in other ways, for example after a
rework or a re-entry from T9, and the prerequisites hold in every case.

**What a pass or exception hands forward.** Each terminal's spec lists the values it emits. When
you decide pass or exception, the form asks for any of them that no artifact already supplies (at
T0, the risk tier). They become the evidence later terminals check, update the use case's profile,
and at T0 set the risk tier for the rest of the lifecycle. An exception hands forward the same values
as a pass: it accepts a gap in the checks, not missing results.

A **clarification** is not a decision: the agent asks for missing information, the addressed role
answers, and the same run continues without counting as a rework.

## 3. Installing and starting

You need [uv](https://docs.astral.sh/uv/), git and GNU make; Docker with Compose v2 if you use
Docker. Python 3.12 is installed by uv.

### Settings and accounts

```bash
make install
cp .env.example .env                 # replace every REPLACE_ME with a long random value
mkdir -p ~/.config/adlc
cp deploy/accounts.example.yaml ~/.config/adlc/accounts.dev.yaml
# in .env: ADLC_ACCOUNTS_FILE=<absolute path of that file>
uv run adlc-account hash             # for each account: paste the output into credential_hash
set -a; source .env; set +a; uv run adlc-account check
```

The accounts file lives **outside the repository**. Each account has a name, a display name, its
roles and a password hash. `ADLC_ENV` is `dev` or `demo`. Never commit `.env` or the accounts file.

Agents need a model provider key in `.env` (for example `ADLC_OPENAI_API_KEY` with
`ADLC_MODEL_PROFILE=dev`, or `ADLC_ANTHROPIC_API_KEY` with `ADLC_MODEL_PROFILE=default`).

### With Docker

```bash
make up          # migrate, register the specs, start every service; returns when healthy
make status      # health of every service
make down        # stop (data kept)
```

### Without Docker

```bash
make local       # set up the database and the specs, then start every process in one terminal
```

Ctrl-C stops everything; data stays in `data/local/`. See `docs/run-without-docker.md`.

### Where things are

| What | Address |
| --- | --- |
| Web application | `http://localhost:8501` (`ADLC_UI_PORT`) |
| Platform API | `http://localhost:8000` (`ADLC_API_PORT`), health at `/health` |
| Traces (Phoenix) | `http://localhost:6006`, project `adlc-platform` |

## 4. Using the web application

### Signing in

Open the web application and sign in with your account name and password. Your name and roles show
in the sidebar; **Sign out** ends the session. A session lasts at most `ADLC_SESSION_TTL` (8 hours
by default); when it expires you are asked to sign in again.

The sidebar has four sections: **Work** (Inbox, New use case), **Delivery** (Use cases, Journey,
Activity), **Insights** (Portfolio) and **Operations** (Dead letters).

### Inbox

Everything waiting for you, grouped: **Sign-offs**, **Clarifications**, **Escalations**,
**Waivers**, **Blocked runs**, **Dead letters** (CoE) and **Change requests** (the ITSM owner
role). It refreshes every 30 seconds and on **Refresh**. Pick an item and **Open** it.

### Submitting a use case (T0)

**New use case**: give it a name and the intake text (what the agent should do, for whom, the data
involved, the expected benefit; at least a few sentences). **Submit**. The T0 intake agent builds
the intake card; when it is ready, the business owner gets a sign-off in the inbox.

### The run page

Open from the inbox or from a use case. At the top: the run, terminal, state, due date and cost.

- **Left**: the artifacts. You may correct an artifact while the run awaits your sign-off (tables
  up to 1,000 rows are editable in place; larger ones are read-only with a spreadsheet upload).
  Saving records a human version beside the agent's and re-runs the controls; deciding is possible
  again once they finish.
- **Right**: the reviewer recommendation, the control results and the **Decision** form.
- **Tabs below**: prerequisites, citations (the sources the agent used), prior rework,
  clarifications, approvals, waiver, activity, timeline and evidence.

**Deciding**: choose the outcome; the form asks only for what that outcome needs (comment, root
cause, reason, rework target, values, waiver details). **Submit decision**. If someone changed the
run while you were reading, the page reloads with a message; check it and decide again.

The run stays in the page address (`?run=…`), so you can share a link to it.

### Clarifications

When an agent needs information it cannot find, the addressed role gets a **Clarification** item
with numbered questions. Answer each one and **Send answers**. The same run continues; it does not
count as a rework.

### Escalations

A run escalates after too many reworks or when it is late. The accountable role opens the
**Escalation** item, resolves the issue and **Completes** it; the run then goes to sign-off.

### Exceptions and waivers

To accept a gap, an approver decides **Exception** with the waiver details and any values the
terminal hands forward (asked for in the same form). A different person with a waiver approver role
(for example the risk owner) opens the **Waiver** item and approves or rejects it; on approval the
run closes and hands those values forward. Approved waivers are checked again at T6 and expire on their date.

### Change requests

At release (T6, T7) an agent raises an ITSM change request. The ITSM owner role (the release
manager) approves or rejects it from the inbox's **Change requests**, with a comment; the runs
waiting for it then re-run their checks.

### Use cases, Journey, Activity, Portfolio

- **Use cases**: yours or all; for each, its journey (runs with times and cost) and **Verify the
  ledger for this use case** (checks the hash chain of its decisions).
- **Journey**: a lane per terminal and a bar per run, with arrows for reworks, reroutes,
  exceptions, events and re-entry; a KPI strip (reworks, escalations, clarifications, time spent by
  agents and people); refreshes every `ADLC_UI_DASHBOARD_REFRESH`.
- **Activity**: what agents and people did, filterable by use case, terminal, actor and step.
- **Portfolio**: KPIs across use cases, by risk tier and status.

### Dead letters (CoE)

Events the platform could not deliver after its retries: attempts, error and re-queue count; the
payload and history on request; **Re-queue** (CoE role only).

## 5. A use case's journey, end to end

1. **T0**: the business owner submits; the intake agent builds the card; the owner passes it and
   sets the risk tier.
2. **T1**: the requirements agent proposes requirements and KPIs; the product owner may send them
   back (rework, root cause *requirement*, with a comment); the agent reworks using the comment;
   the product and business owners pass.
3. **T2**: the architect agent may ask a clarification (for example the data retention period);
   the addressed role answers; the design is signed off.
4. **T3**: the builder produces the pilot agent and its package hash.
5. **T4**: evaluation; a defect with root cause *implementation* sends the work back to T3; T3 run 2
   and T4 run 2 pass.
6. **T5**: assurance; a gap that cannot be closed yet becomes an exception with a waiver.
7. **T6**: readiness checks the evidence chain, the hash and the waiver; the release manager
   approves the change request; release is authorised.
8. **T7**: canary then full rollout of exactly the hash T4 tested; hand-over.
9. **T8**: operations; a monitor raises an event (for example drift after a model change).
10. **T9**: the change is classified and the use case re-enters at an earlier terminal, or is
    retired.

## 6. Operating the platform

| Task | How |
| --- | --- |
| Health | `make status`; `GET /health` on the API; `uv run adlc-orchestrator health` |
| Traces | Phoenix at port 6006: every agent call, tool call and policy check |
| Verify the ledger | `uv run adlc-ledger verify` (all) or `--usecase UC-0001`; `--json` for scripts. Exit 1 means a break: something was changed or removed |
| Trace a use case | `make trace USECASE=UC-0001`: every decision linked to spec version, person and evidence hash |
| Specs | `make spec-validate`, then `make spec-register` after changing `adlc-specs/` |
| Accounts | edit the accounts file; `uv run adlc-account hash` for a password; `adlc-account check` |
| Backups | the database and the evidence file store together, at the same point in time (`deploy/README.md`) |
| Reset | `make reset` wipes all data after you type the environment's name |

## 7. Running the demo

The demo walks the Incident Triage use case through T0–T9 and shows every demo moment (D-1 to D-9:
human decisions everywhere, rework with a comment, root-cause routing, escalation after three
reworks, an exception with a waiver, package hash integrity, an operations event leading to
re-entry, the live dashboard, and a clarification). The agents' replies are rehearsed recordings,
so the demo is the same every time; everything else runs for real.

```bash
# demo environment: ADLC_ENV=demo in .env
make demo-reset          # wipes the platform and pilot data
make demo-auto           # rehearsal: the driver takes every human step
make demo                # presenter: the driver says what to do and as whom, and waits
make demo-live           # presenter, with real models instead of the recordings
make demo FROM_STEP=9    # resume after a stop
```

Keep **Journey** open; switch to the **Inbox** for each human step. The presenter guide is
`demo/README.md`.

## 8. Limits and troubleshooting

- Anyone with write access to the database file could bypass the ledger's triggers; `adlc-ledger
  verify` still detects any change. Signed evidence comes later.
- A sign-out is not remembered across an API restart; sessions expire after `ADLC_SESSION_TTL`.
- No lockout after failed sign-ins (every failure is logged).
- Plain HTTP on one private network; one host (SQLite allows one writer at a time).

| Symptom | Likely cause |
| --- | --- |
| A port is taken | change `ADLC_API_PORT`, `ADLC_UI_PORT` or `ADLC_PHOENIX_UI_PORT` in `.env` |
| The orchestrator does not start | no model provider key for the profile's tiers |
| "The platform refused this: not allowed" | your account lacks the role for that action |
| A run stays **blocked** | open it: the page names the missing prerequisite or approval |
| The page reloads with "this run changed" | someone acted first; check and decide again |
