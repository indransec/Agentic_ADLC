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
