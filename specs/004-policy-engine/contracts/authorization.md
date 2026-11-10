# Contract: Authorization

```text
authorize(actor, action, resource, context) -> bool
authorize_decision(actor, action, resource, context) -> (allowed: bool, reason: str)
```

## Request

- The request string is `<action>:<resource>`, for example `write:T1.artifacts`,
  `read:ledger.T0` or `deploy:prod`.
- Tool use is `mcp:<server>:<operation>`, for example `mcp:jira:read`.

## Decision order

1. **Run scope.** The actor must be bound to `context.run_id`. An actor id has the form
   `<kind>:<run_id>` (`agent`, `reviewer`, `tool`). A missing run, or an actor bound to another
   run, gives **refused**: `out of scope: <actor> is bound to <run>`.
2. **Tool use.** For a request starting `mcp:`, a matching deny pattern refuses it. Otherwise it
   is allowed if it matches an entry of the run's terminal spec `authorities.tool_scopes`, and
   **refused** if not: `tool not in scope: <request>`.
3. **Deny list.** If any `authorities.deny` pattern matches, the request is **refused**:
   `denied by <pattern>`.
4. **Allow list.** If any `authorities.allow` pattern matches, the request is **allowed**:
   `allowed by <pattern>`.
5. **Default.** The request is **refused**: `no allow entry matches <request>`.

Patterns use shell-style wildcards (`*`, `?`) over the whole request string. `read:ledger.all`
in a spec is read as `read:ledger.*` (the spec convention).

## Properties (hypothesis)

- If any deny pattern matches, the result is refused, whatever the allow list holds.
- A request that matches no allow pattern is refused.
- An actor bound to another run is always refused.
