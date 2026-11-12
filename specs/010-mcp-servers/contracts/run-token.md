# Contract: Run Token (feature 010, research R-02)

**Format**: `v1.<claims>.<signature>`; `claims` is base64url (no padding) of canonical JSON
(sorted keys, no spaces); `signature` is base64url HMAC-SHA256 over `v1.<claims>` with
`ADLC_TOOLS_TOKEN_KEY`.

**Claims**

| Claim | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | The run the call is for, or `platform` for evidence reads |
| `usecase_id`, `terminal_id` | string | From the run |
| `attempt` | int | Agent attempt |
| `scopes` | list of `mcp:<server>:<scope>` | The terminal's tool scopes from the pinned spec |
| `bound` | object | `branch`, `authorised_hash`, `candidate_hash`, `environment` when they apply |
| `iat`, `exp` | int (Unix seconds) | `exp` = `iat` + 300 |

**Server checks, in order** (each failure is `not permitted`, logged with the reason, never with
the token):

1. Format and version `v1`.
2. Signature (constant-time compare).
3. `exp` in the future and `iat` not more than 60 s in the future.
4. `mcp:<server>:<tool's scope>` in `scopes`.
5. The tool's bound values present where required (e.g. `cd_deploy` needs `authorised_hash`).

**Platform rules**: one token per call; minted only after the tool gate allowed the call; never
logged, traced or stored.
