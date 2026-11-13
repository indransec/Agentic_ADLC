# Contract: demo commands (feature 014)

| Command | Does |
| --- | --- |
| `make demo` | Stops the orchestrator, runs the driver in presenter mode with rehearsed replies |
| `make demo-auto` | Same, `--auto` (the driver takes the human steps) |
| `make demo-live` | Presenter mode with the configured models (`--live`) |
| `make demo-reset` | Full reset; refused unless `ADLC_ENV=demo`; asks to confirm |
| `make resilience` | The three resilience checks on the running stack (`demo` only) |
| `make trace USECASE=UC-n` | `adlc-ledger trace UC-n` |

`adlc-demo [--auto] [--live] [--from-step N] --script demo/script.yaml`: exit 0 when every step
met its expectation; the report (markdown and JSON) lists D-1 to D-9 with evidence. Stdout lines
`fault <name> <action>` ask the wrapper for a fault; the wrapper answers `done` on stdin.
