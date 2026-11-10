# Synthetic data (demo only)

Stand-in evidence and artifacts used until real agents (feature 006) and real evidence sources
(features 009–012) exist. The policy engine labels every decision that reads this data as
`synthetic` in its decision record and in the run's control results, so a gate passed on
stand-in data is always visible. Set `ADLC_SYNTHETIC_DIR=off` to disable it.

- `evidence.yaml`: values for `env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`,
  `template`, `dataset`, `release`, `portfolio`, `retirement` and `directory`.
- `artifacts/T<n>.yaml`: artifacts that meet the terminal's blocking controls. The stub agent
  starts from them.
