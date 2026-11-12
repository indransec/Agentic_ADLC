# Quickstart: Terminal Agents T6–T9 (feature 012)

- Offline (CI `make check`): T6–T9 integration tests with scripted replies; the monitor evaluator
  raising drift after the model swap on the fake pilot; change approval and proposed-event APIs;
  the reference replay through T9 re-entry.
- Live (optional, dev model): `adlc-replay --recording /replays --profile dev --live-rest --only
  it-service-desk` with the stack up and traffic running; approve the change in the inbox; trigger
  `pt pilot-fault model_swap trigger` and watch the drift event open T9.
