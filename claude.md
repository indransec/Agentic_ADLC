# Agentic ADLC platform
- Architecture: docs/solution-architecture.md (sections referenced as SA §n); terminal specs: docs/terminal-design-spec.md
- Build plan and feature order: docs/build-plan.md. Work on one Spec Kit feature at a time.
- Terminal specs (runtime YAML) live in adlc-specs/, never in specs/ (Spec Kit owns specs/).
- Never hard-code terminal-specific or use-case-specific values in code.
- Naming: SA Annex A. Python 3.12, typed, uv. CI runs `make check` on every push; run the relevant test suites locally while working.
- Settings: environment only (`.env`, see `.env.example`); `ADLC_ENV` is `dev` or `demo`. Local accounts live in the file at `ADLC_ACCOUNTS_FILE`, outside the repo; roles come from `adlc-specs/shared/roles.yaml`.
- Every endpoint needs a session except those in `PUBLIC_PATHS` (`src/adlc/api/auth.py`); ledger rows are append-only for every DB identity.
