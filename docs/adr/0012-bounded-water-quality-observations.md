# ADR 0012: Bounded Water Quality observations

Status: Accepted

Date: 2026-09-22

## Context

ADR 0011 established sampling-point evidence and identity. Actual results require
determinand/unit semantics and the publisher's Sample/Sampling relationship chain.
The [live contract assessment](../data-sources/environment-agency-water-quality-observations.md)
found no publisher snapshot token or sort option, and timestamps without a timezone.

## Decision

Accept one exact sampling point and determinand per immutable retrieval, with
start-inclusive/end-exclusive date bounds spanning 1–31 days. Bound requests to
20 observation pages, 5,000 records, 20 referenced units, 16 MiB per response and
64 MiB combined. Fetch the determinand and referenced unit codelists alongside results.
Construct fixed HTTPS URLs; do not follow publisher pagination links or redirects.
Validate totals, identities, relationships, scope, headers, quantities and evidence hashes.

Preserve timestamp and result text, numeric value and censored bounds separately.
Do not assign UTC, convert units or infer geographic/company relationships. Retain
publisher Sample/Sampling IDs and nested material/purpose metadata.

Migration 0008 adds retrieval, unit and observation tables. Publication references a
compatible stored sampling point, inserts atomically and verifies stored children on
exact retries. Changed evidence coexists. Application privileges remain SELECT only;
ingestion receives SELECT and INSERT. Public reads require a retrieval UUID and use
bounded identity keyset pagination. The existing refresh supervisor controls retrieval.

## Consequences

This supports reproducible bounded historical results, including empty windows and
corrections, without claiming a complete archive or publisher-atomic pagination.
Unexpected timezone/qualifier/relationship formats fail closed pending source review.
Observation freshness is not inferred from metadata freshness. Scheduling and broader
archive traversal remain separate deployment/design decisions.
