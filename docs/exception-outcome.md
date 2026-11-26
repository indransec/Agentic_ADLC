# The exception outcome: how it works and what it does not do

Status: describes the platform **as built** (2026-11-24), with known gaps and open options at the end.
Sources: `adlc-specs/terminals/T*.yaml` (`outcome_model.exception`, `prerequisites`), `src/adlc/orchestration/states.py`,
`src/adlc/orchestration/engine.py`, `src/adlc/policy/predicates/records.py`, `src/adlc/inbox/rules.py`.

## What exception means

One of the five outcomes (pass, rework, exception, escalate, terminate). It means **proceed despite a known gap, under
a documented, time-limited waiver**. It is the only outcome that both moves the use case forward and records that
something is missing.

- **People only.** Agents can never set pass, exception or terminate (rule V-09); the reviewer only recommends.
- **Per terminal.** Each spec's `outcome_model.exception` says whether it is allowed, when, and what it requires.

| Terminal | Allowed when | Required fields | Routes to |
|---|---|---|---|
| T0, T1, T2 | Any time | waiver_owner, expiry, compensating_control | The next terminal |
| T3 | Any time | The same three | T4 (spec `recheck_at: [T6]`) |
| T4 | Only if no critical threshold was missed | The same three | T5 (`recheck_at: [T6, T8]`) |
| T5 | Only the `risk_owner` may approve | risk_acceptance, expiry, compensating_control | T6 (`recheck_at: [T6, T8]`) |
| T6 | Go with conditions (e.g. a limited rollout) | conditions, expiry | T7 |
| T7 | **Never** (`not_allowed: true`) | | |
| T8 | A known issue is tolerated | waiver_owner, expiry | Monitoring continues |
| T9 | Emergency changes only | retrospective_plan | The re-entry terminal |

## What the waiver fields stand for

Together the fields answer **who** owns the gap, **what** protects you meanwhile, and **until when**.

| Field | Stands for | Example | How the platform uses it |
|---|---|---|---|
| `waiver_owner` | The person accountable for closing the gap before the expiry | `solution_architect-person` | Recorded on the waiver and shown to the approver. Not used for alerts: T8 MON-09 alerts the owning terminal's owner, not this person |
| `expiry` | The date the waiver stops being valid: the deadline to close the gap | `2027-03-31` | **The only field checked later.** T6 CTL-T6-02 blocks release if any waiver expires before the release date; T8 CTL-T8-04 blocks a monitoring review while any waiver has expired; T8 MON-09 alerts 14 days before expiry. Without it, an exception would quietly become permanent |
| `compensating_control` | The temporary safeguard that makes the risk acceptable while the gap is open | "Every agent answer is reviewed by a person before sending"; "Rollout limited to 10% of users" | Free text, stored on the waiver and shown to the approver, who judges whether it is adequate. **Never checked automatically afterwards** (gap 3 below) |

Some terminals use other fields in place of these:
- **T5** requires `risk_acceptance`: the risk owner's formal acceptance of the residual risk.
- **T6** requires `conditions`: the limits the release goes ahead under, such as a rollout cap.
- **T9** requires `retrospective_plan`: how an emergency change will be validated afterwards.

## How it is granted: two people

1. A sign-off person decides **exception** with the required fields, plus any value the terminal's pass `emits` that no
   artifact supplies (for example `risk_tier` at T0): an exception waives controls, not the hand-off. The decision is
   recorded, a waiver (W-n) is proposed, and the run stays in *awaiting sign-off*.
2. A **different** person with a waiver-approver role approves it on the Waiver page. The approver role is the
   exception's `set_by` role when the spec names one, otherwise the terminal's accountable roles.
   - **Approved:** the run closes with status `exception` and emits `Tn.exception`, which routes onward (usually
     where a pass would go). It emits the same values a pass would, taken from the decision fields kept with the
     waiver, so the use-case profile gets a new version and T0's `risk_tier` sets the use case's tier.
   - **Rejected:** the run returns to awaiting sign-off.
   - **An artifact is edited while the waiver is pending:** the waiver is withdrawn automatically, because the approver
     would otherwise approve content that changed after the waiver was proposed. Someone must decide exception again.

## What the next terminal's prerequisites see

- **The status check passes.** Every terminal's first prerequisite accepts both statuses, e.g.
  `T2.status in ["pass", "exception"]`. T6 checks the whole chain:
  `all_statuses_in(["T0".."T5"], ["pass", "exception"])`. `is_signed` and `is_live` also count an exception as signed.
- **Evidence checks behave exactly as after a pass.** Checks like `evidence_exists(T2.tool_api_contracts)` look only at
  whether the artifact exists, never at the previous status or its waiver.
- **A missing artifact is not excused.** What happens depends on the prerequisite's `on_missing` setting:
  - **`block`** (31 of 33 prerequisites): the new run goes to **blocked**. No agent runs. The run page and Inbox show
    which prerequisite failed. A blocked run cannot be waived past; it can only be terminated by the business owner.
    To recover, the previous terminal must produce the artifact (normally through a rework decision routed back to
    it). When that terminal closes again, its event reopens the blocked run, which re-checks its prerequisites.
  - **`warn`** (PRE-T6-03 `change.window_requested`, PRE-T9-03 `T4.regression_pack`): the run continues and a
    warning is recorded.

**In short:** an exception lets the use case move on; it never exempts the next terminal's prerequisites.

## How waivers are checked downstream

The evidence source `waivers` holds every **approved** waiver of the use case.

| Where | Check | Effect |
|---|---|---|
| T6 | CTL-T6-02 `no_waiver_expiring_before(release_date)` | Blocks release if any waiver expires before the release date |
| T6 | evidence-auditor helper agent | Reviews chain completeness and waiver expiry |
| T8 | CTL-T8-04 `no_expired_waivers()` | Blocks a monitoring review while any waiver has expired |
| T8 | MON-09 `waiver_expiring_within("14d")` | Raises `T8.event.waiver_expiring` to the owning terminal's owner |

## When to grant one in practice

Grant an exception when the work is good enough to move on, the gap is known and bounded, and someone accountable
accepts it until a stated date. Typical cases:

| Terminal | Typical situation |
|---|---|
| T0 | The business case is sound; one item, such as a value estimate awaiting finance sign-off, is pending |
| T1 | One requirement is open (e.g. a retention rule awaiting legal); the rest are clear enough to design against |
| T2 | A secondary integration's design is deferred to a later phase |
| T3 | A non-critical code-quality finding is accepted, such as known lint debt or a dependency update next sprint |
| T4 | An advisory target was missed (e.g. 0.88 against 0.90); every critical threshold passed |
| T5 | A residual risk is formally accepted by the risk owner (e.g. a medium risk mitigated by human review) |
| T6 | Go with conditions: 10% rollout or business hours only until the run-book is complete |
| T8 | A known issue is tolerated (slight drift, a minor cost overrun) while a fix is planned |
| T9 | An emergency change, such as a security patch, is shipped first and validated afterwards |

Do **not** grant one when:
- **An artifact the next terminal needs is missing.** The next run will block anyway.
- **A critical threshold failed (T4), or the risk is unacceptable (T5).** These lead to rework or terminate.
- **The gap has no owner or no end date.** That is a permanent risk, not a waiver.
- **The proposer would approve it themselves.** The platform refuses this.

The test: can you name **who** owns the gap, **what** protects you meanwhile, and **when** it must close? If all
three have a clear answer, an exception fits; otherwise choose rework.

## Known gaps (as built)

1. **`recheck_at` is stored but unused.** It is copied onto the waiver record, but no code reads it. The T6 and T8
   controls check every approved waiver, whatever its `recheck_at`.
2. **Only the expiry date is re-checked.** Nothing re-tests whether the compensating control or risk acceptance still
   holds.
3. **No warning at decision time.** When exception is chosen, the platform does not check whether the next
   terminal's prerequisites will be met; the person learns only when the next run blocks.

## Options (not decided)

1. **Check when the exception is chosen** (recommended). Before an exception is recorded, evaluate the next terminal's
   prerequisites and refuse, or warn, if one would block. A missing artifact still always blocks, and the person
   finds out early.
2. **Let a waiver cover a named prerequisite.** For example, allow `waives: [PRE-T3-02]` on the exception, so that
   blocking prerequisite becomes a warning while the waiver is valid. More flexible, but it weakens the chain of
   evidence and needs spec changes plus a validation rule.

Either option, and fixes for gaps 1 and 2, would be a separate Spec Kit feature.
