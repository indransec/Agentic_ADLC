# Quickstart: End-to-End Demo (feature 014)

- Offline (CI): the driver in `--auto` over the fake pilot; scenarios D-1 to D-9; negatives.
- Live: `ADLC_ENV=demo`, `make demo-reset`, `make demo-auto` (rehearsal) or `make demo`
  (presenter), the web app's Journey page open; then `make trace USECASE=UC-1`; `make resilience`.
