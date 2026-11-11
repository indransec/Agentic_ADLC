---
title: "Data classification policy"
data_class: internal
synthetic: true
collections: []
version: "1.0.0"
---
# Data classification policy

## Classes

Data classes from least to most sensitive: public, internal, synthetic_or_masked,
confidential_masked, confidential, restricted.

## Claims data

Claims history and claim documents are confidential; masked copies used for AI processing are
confidential_masked. Owner: head of claims operations (data owner role). Access for AI agents is
approved for masked copies only.

## Policy and product data

Policy terms and product catalogues are internal. Owner: product management.

## IT service data

Service desk tickets are internal; tickets may contain personal data that must be masked before
processing (synthetic_or_masked). Owner: IT operations director.

## Credit data

Credit bureau reports and income data are restricted. Owner: chief credit risk officer. AI access
requires model risk approval and is not pre-approved.
