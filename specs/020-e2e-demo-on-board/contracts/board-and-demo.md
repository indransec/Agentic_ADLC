# Contract: the change kind, the driver on the board, the reset (020)

## Board

| Item | Parent | Platform writes | People change |
| --- | --- | --- | --- |
| Change Request | the run's item | title, description (summary, risk, window, waiting run, deciding role), state, change id | the decision field (Approve change / Reject change) and comment |

Outcomes of a change decision (inbound): accepted (`decide_change:approve` / `:reject`);
refused `not_authorised` (not the ITSM owner role), `stale` (already decided), `unknown_value`
(a run decision on a change, or a change decision on a run). Each refusal: comment, field cleared.

## Simulator CLI

| Command | Does |
| --- | --- |
| `ado-sim token import <unique_name> --stdin` | registers the token read from stdin (≥ 40 characters) for that user; never prints it; refused for an unknown or inactive user or a token already registered |

## Demo

| Command | Board on | Board off |
| --- | --- | --- |
| `make demo` / `demo-auto` / `demo-live` | human steps on the board (presenter told where and what; auto as each person) | 014 behaviour |
| `make demo-reset` | + imports the sync's and the people's tokens, sets page passwords | 014 behaviour |
