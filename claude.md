# Agentic ADLC platform
- Architecture: docs/solution-architecture.md (sections referenced as SA §n); terminal specs: docs/terminal-design-spec.md
- Build plan and feature order: docs/build-plan.md. Work on one Spec Kit feature at a time.
- Terminal specs (runtime YAML) live in adlc-specs/, never in specs/ (Spec Kit owns specs/).
- Never hard-code terminal-specific or use-case-specific values in code.
- Naming: SA Annex A. Python 3.12, typed, uv. Run `make test` before saying a task is done.