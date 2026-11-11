---
id: PB-T0-03
version: "1.1.0"
title: Risk classification
owner_role: adlc_coe
status: active
---
# Risk classification

## Purpose

Assign the use case a risk tier (`low`, `medium` or `high`). The tier selects parameters for every
later terminal: test counts, thresholds, autonomy limits and sign-off rules.

## Dimensions and criteria

Rate each dimension; the dimension's tier is the first row that matches.

| Dimension | high | medium | low |
| --- | --- | --- | --- |
| `customer_impact` | Decisions affect money, eligibility or safety of customers | Customer-facing advice or drafts reviewed by staff | Internal productivity only |
| `autonomy` | Acts without a person in the loop on irreversible actions | Acts on reversible actions or proposes for approval | Assists a person who decides |
| `data_sensitivity` | Confidential or restricted data, health or financial records | Personal data, masked or minimised | Public, internal or synthetic data |
| `regulatory` | A regulator requires explainability, audit or approval (credit, insurance pricing, employment) | Sector conduct rules apply | No specific regulation |
| `scale` | More than 10,000 decisions per month | 1,000 to 10,000 per month | Fewer than 1,000 per month |
| `reversibility` | Harm cannot be undone | Harm can be undone with effort | Harm is negligible or easily reversed |

## Steps

1. One `risk_classification` row per dimension with `rating` (the matched criterion in a few
   words), `rationale` (the fact and its source) and `tier`.
2. Add a final row with dimension `overall`: its tier is the highest of the dimension tiers.
3. Use the AI policy and data classification policy from the knowledge sources where they set a
   tier explicitly (they take precedence; cite them).

## When to ask

Ask the business owner when the volume, the decisions taken, or whether a person approves them is
unknown. Ask the role that owns the data when its classification is not in the policy.
