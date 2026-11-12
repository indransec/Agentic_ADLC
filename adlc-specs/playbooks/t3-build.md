---
id: PB-T3-01
version: "1.1.0"
title: T3 build
owner_role: adlc_coe
status: active
---
# T3 build

## Purpose

Turn the approved design into one immutable candidate package: the golden template with the use
case's fill, built and tested by CI, running in dev. Its package hash is what T4 evaluates, T5
assures, T6 authorises and T7 deploys.

## Inputs

- T1: functional requirements, autonomy levels, evaluation and RAI thresholds, KPIs.
- T2: design decisions, tool and API contracts, human-in-the-loop design, token budget.
- On rework: the defect log (root cause `implementation`) and the approvers' comment.

## Procedure

1. `git_list` and `git_read` the fill files on `main` (the template's example fill).
2. Adapt them to T1 and T2 following the golden template playbook (PB-T3-02): instructions,
   routing rules, tool bindings, thresholds and settings. Change only what the requirements,
   design or defects call for.
3. `git_write` all changed files in one commit with a message naming the requirements it serves;
   give `parent` (the commit you read) when the branch already exists.
4. `git_open_pull_request` with a title and a description listing the changes.
5. `ci_run`. If a check fails, read its detail, fix the named fill part, write again and run CI
   again. Stop after three failed rounds and report the last CI detail as the blocker.
6. `pilot_env_create` with the package hash CI returned, then `pilot_env_status` to see it
   running and healthy.
7. Optionally `prompt_registry_write` the instructions text and `artifact_store_write` build notes;
   use their sha256 in the manifest.

## Steps per artifact

1. **build_manifest** (`item, name, version, hash`): one row each for the template (name and
   version from `pilot_env_infra`), the instructions (prompt registry sha256), every tool binding,
   and the package (`package`, CI's hash). Every row has a version and a hash.
2. **traceability_matrix** (`req_id, component, prompt_id, tool_id, test_id`): one row per T1
   functional requirement; `test_id` names the CI suite that covers it (`package`).
3. **design_conformance** (`decision_id, implemented, deviation, approver`): one row per T2 design
   decision; `implemented` true or false; any deviation explained, with `approver` null.
4. **test_results** (`suite, total_count, passed_count, failed_count, coverage_pct`): CI's `tests`,
   one row per suite, copied exactly.
5. **security_build_checks** (`scan, tool, critical_count, high_count, medium_count, status`): CI's
   `scans` copied exactly: `sast` (tool `bandit`) and `secret_scan` (tool `pattern-scan`);
   `status` is `pass` when the scan's check passed.
6. **observability_check** (`signal, emitting, sample_trace_id`): CI's `observability` rows copied
   exactly (`traces`, `rai_metrics`).
7. **config_register** (`config_key, environment, value_ref, autonomy_related`): every fill setting
   you set (for example `token_budget`, `model_mode`, review thresholds), `environment` `dev`,
   `value_ref` the fill file and key; `autonomy_related` true for review and auto-assignment
   thresholds.
8. **change_log** (`change_id, description, req_id, pr_link`): one row per change, with the
   requirement it serves and the pull request id.
9. **candidate_package** (`package_uri, sha256`): one row: `pilot-registry://<hash>` and CI's hash.

## Limits

- Never change files outside the fill layout; CI refuses them.
- Never put keys, tokens or passwords in a fill; the secret scan fails the build.
- The package hash in every artifact is exactly CI's.
