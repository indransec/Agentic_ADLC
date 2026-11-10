# Contract: Verification

```text
Verifier.verify(scope: "UC-nnnn" | "all", actor: str) -> Report
Report: {scope, records_checked, verified: bool, breaks: [{ledger_key, check, element, expected, actual}]}
```

## Checks per record (in chain order per use case)

| Check | Applies to | Break when |
| --- | --- | --- |
| `content` | All records | `sha256(normalise(content_json))` differs from `content_hash` |
| `chain` | All records | `previous_record_hash` differs from the prior record's `content_hash` (or is not null for the first record) |
| `artifact` | Version-2 records | An artifact `content_hash` is missing from the store, or its stored body re-hashes differently |
| `attachment` | Version-2 records | A file is missing, or its bytes re-hash differently |
| `binding` | Version-2 records whose spec binds | `bound_to` differs from the bound terminal's package hash, read from the stored artifact content that the bound terminal's latest earlier record references |

Breaks never include artifact content: only keys, hashes and names.

## Operations

| Interface | Usage |
| --- | --- |
| CLI | `adlc-ledger verify [--usecase UC-nnnn] [--json]`; exits 0 when verified, 1 with breaks, 2 on configuration errors |
| Service | `LedgerService.verify(actor, scope)` for any signed-in person (007 and 013) |

Verifying `all` is one call and one row. Each call writes one `ledger.verification_run` row: actor (the account, or `cli:<os user>`),
scope, times, the count of records checked, breaks, and whether it verified.
