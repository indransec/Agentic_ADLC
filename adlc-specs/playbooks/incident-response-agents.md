---
id: PB-T8-02
version: "1.1.0"
title: Incident response agents
owner_role: adlc_coe
status: active
---
# Incident response agents

## Purpose

Make every operational problem a tracked incident with a severity, and stop harm fast when the
agent itself is the cause.

## Steps

1. A problem seen in the reading or the traces without an incident: `servicenow_incident_create`
   with a summary, a severity (1 critical harm or leakage; 2 major degradation; 3 minor; 4
   cosmetic) and the evidence (metric, value, time).
2. A critical safety breach (personal data leaked, harmful output): `kill_switch_invoke` with the
   reason, then a severity-1 incident. Only a person releases the kill switch.
3. Record every incident in `incident_problem_log`; an open sev1 or sev2 keeps the review from
   passing until it is closed.
