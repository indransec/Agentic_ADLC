# Contract: Evidence

```text
class EvidenceProvider(Protocol):
    get(source: str, context: EvalContext) -> Evidence | NOT_AVAILABLE
```

## Namespaces (what an expression may read)

| Root | Provided by | Value |
| --- | --- | --- |
| `T<n>` | SQL provider | Terminal evidence of `T<n>` for this use case (below) |
| `run` | SQL provider | `rework_count`, `age` (duration since open), `now`, `usecase_id`, `run_version` (`run-<k>`), `risk_tier`, `mode` |
| `intake` | SQL provider | `free_text` (intake text), `business_owner` (submitter account), `title` (name) |
| `trigger` | SQL provider | `event_id`, `severity` (from the payload when present), `evidence` (the operational event payload, or the causing run's ledger key) |
| `timeline` | Pinned spec | The timeline for the use case's tier. Durations are CEL durations; non-duration values (`window_end`) are strings |
| `tier` | Pinned spec | The terminal's `controls.tiering[<tier>]` mapping, or an empty mapping |
| `param` | Frozen parameter set | `{name: value}` |
| `profile` | `ProfileSource` | Not available until feature 005 |
| `directory` | `Directory` | Account names |
| `env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`, `template`, `dataset`, `release`, `portfolio`, `retirement` | Later features; synthetic provider meanwhile | Fields from `evidence_sources.yaml` |

## Terminal evidence `T<n>`

From the latest closed run of `T<n>` for the use case. When `T<n>` is the run's own terminal, it
comes from the run being checked, whose `status` is `open`.

| Member | Meaning |
| --- | --- |
| `status` | Final status (`pass`, `exception`, `rework`, `terminate`) |
| `signed_by` | Account names of the pass sign-offs |
| `closed_at` | Timestamp |
| `run_version` | `run-<k>` |
| `waivers` | Approved waiver ids of the run |
| `bound_to` | The terminal spec's `evidence.ledger.bound_to` reference resolved in this use case (for example the T3 package hash) |
| `<artifact>` | A list of row mappings |
| `<emitted name>` | The value emitted in the pass decision (for example `eval_baseline`) |

A terminal with no closed run is `NOT_AVAILABLE`, unless it is the run's own terminal.

## Values

- Numbers in text form (`"80"`, `" 0.02 "`) count as numbers. Values with units (`"80%"`)
  don't.
- Truthy values are `true`, and the text `"true"`, `"yes"` or `"1"` (case-insensitive).
- A row is **open** when its `status` is `open`, or when it has a `closed` column that is empty.

## Synthetic provider

- **Data**: read from `ADLC_SYNTHETIC_DIR` (default `data/synthetic`). The value `off`
  disables it.
- **Layering**: `CompositeEvidenceProvider(real, synthetic)` uses a real value when there is
  one, otherwise the synthetic one, which it marks `synthetic=True`.
- **Labelling**: a decision with any synthetic input is labelled synthetic (FR-025).
