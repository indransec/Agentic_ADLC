# Quickstart: validating the Terminal Spec Toolkit (002)

These steps prove each user story. Commands and outputs are defined in
[contracts/adlc-spec-cli.md](contracts/adlc-spec-cli.md); routing expectations are in
[contracts/spec-registry-interface.md](contracts/spec-registry-interface.md).

## 1. Validate the folder (US1, US2, US3)

```bash
make spec-validate                          # or: uv run adlc-spec validate adlc-specs
uv run adlc-spec validate adlc-specs --format json | jq .summary
```

**Expect**: `0 errors`, with a few `V-26` warnings for proposed defaults and some `V-23` info
lines, all in under 10 s (SC-001).

## 2. Every rule catches its fixture (US1)

```bash
uv run pytest tests/unit/spec_toolkit/test_rule_fixtures.py -q
```

**Expect**: one passing case per rule id in contracts/validation-rules.md (SC-002).

## 3. Break a spec on purpose (US1, US6)

Edit `adlc-specs/terminals/T3.yaml`: rename a tool scope to `mcp:gitt:branch_write`, add a
field `rul:` under a control, and change a route without changing the version.

```bash
uv run adlc-spec validate adlc-specs        # expect V-06, S-01, V-24, exit 1
make check                                  # expect failure at ==> spec-validate
git checkout adlc-specs/terminals/T3.yaml
```

In VS Code with the Red Hat YAML extension, the unknown `rul:` field is underlined while you
type (SC-008).

**Result (2026-11-10, manual check by the project owner)**: confirmed. An unknown field added
to `adlc-specs/terminals/T0.yaml` is flagged by the Red Hat YAML extension.

## 4. Conversion record (US3)

Open `adlc-specs/CONVERSION.md`. Each terminal has a row for every TDS trigger,
prerequisite, control, artifact, route and timer (SC-003).

```bash
grep -RnE "rule: '[a-z ]+'$|condition: '[a-z ]+'$" adlc-specs/terminals || echo "no free text"   # SC-004
```

## 5. Register (US4)

```bash
make up                                     # migrate → register → api
make spec-register                          # second run: "0 registered, N unchanged"
```

**Expect**: the first `make up` registers 10 terminals and every catalogue, and the second
registration writes nothing (SC-005). Then try to edit the registry directly:

```bash
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_owner -d adlc \
  -c "UPDATE spec.spec_registry SET version='9.9.9' WHERE terminal_id='T0';"   # refused
```

Bump `T0` to `1.0.1` with a description-only change, then run `make spec-register`.
**Expect**: `T0 1.0.0 → 1.0.1 registered (deprecated 1.0.0)`.

## 6. Route lookups (US5)

```bash
uv run pytest tests/integration/spec_toolkit/test_demo_routing.py -q
```

**Expect**: every row of the demo routing table in the registry contract passes against the
registered specs (SC-007).

## Validation run (2026-11-10, T070)

These results are from a macOS laptop with Docker Desktop, using API port 8010 as for feature 001.

| Step | Result |
| --- | --- |
| 1 Validate the folder | `make spec-validate`: 0 errors, 8 V-26 warnings (proposed-default guardrails), 65 files in 0.7 s (SC-001) |
| 2 Rule fixtures | 45 fixture cases, each caught by its rule (`test_rule_fixtures.py`); rule table matches the code (`test_rules_documented.py`) (SC-002) |
| 3 Break a spec | Covered by fixtures (V-06, S-01) and `test_versioning.py` (V-24). A planted error makes `make check` stop at `==> spec-validate`. Editor highlighting was **not** checked by hand in this run; every YAML file declares its schema (`test_every_yaml_declares_its_schema`) |
| 4 Conversion record | `CONVERSION.md` accounts for every TDS element of T0–T9 (`test_conversion_record.py`, SC-003); no free-text rules (`test_every_expression_parses`, SC-004) |
| 5 Register | `make up` ran migrate → register (55 registered) → api (healthy). Re-registration on restart and `make spec-register`: 0 registered, 55 unchanged, in under 1 s (SC-005). A direct `UPDATE spec.spec_registry SET version=...` as `adlc_owner` was refused (`spec.spec_registry is immutable`) (SC-006) |
| 6 Route lookups | Live SQL: `T4.rework.implementation` opens T3. All demo routing rows (D-2 to D-9) pass against both registries (`test_demo_routing.py`, SC-007) |
| `make check` | Passed in about 76 s: 376 tests, 93% whole-package coverage, 94% gated core modules, migration round trip incl. spec tables, no leaks |
