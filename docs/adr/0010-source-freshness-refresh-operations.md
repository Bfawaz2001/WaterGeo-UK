# ADR 0010: Source freshness and bounded refresh operations

- Status: Accepted
- Date: 2026-09-20

## Context

The four accepted source families have different time semantics. A recent download
can contain old readings; an old static boundary release can still be the reviewed
release. Bounded history describes one requested window, not global coverage.
We need operational visibility and scheduler-compatible refreshes without adding
an always-on scheduling service or widening database privileges.

## Decision

Expose `GET /v1/sources/status`, selecting only versions compatible with the public
APIs. Use one repeatable-read database view and database timestamp. Report availability,
retrieval times, age, observation bounds and counts separately. Return 200 for known
unavailability and sanitized 503 for database failures. Responses use `no-store`.
Keep liveness and schema readiness independent of dataset freshness.

Only Hydrology latest has configurable current/stale classifications. Both retrieval
and observation age limits default to unset (`unknown`). They are operator policy,
not publisher promises. Observation status conservatively uses the oldest latest
reading, with missing values/observations and future timestamps preventing a claim
that all readings are current. Versioned releases/plans and bounded history have
`not_applicable` age classifications, while still exposing their timestamps and ages.

Provide `scripts/refresh_sources.py` with one source per run and explicit history
measure/window arguments. A spawned worker owns a PostgreSQL session advisory lock
for the entire fetch, validation and atomic load. Different sources have independent
locks; all bounded-history jobs share one source lock. Existing loaders retain their
transaction locks and integrity checks. A supervisor enforces the job deadline and
emits progress every 30 seconds. It terminates and, if necessary, kills the worker.

Keep each online run's evidence under a unique directory. Reuse verified local
evidence explicitly for retries. Never delete reviewed or incomplete evidence as
automatic failure cleanup. Publication means the existing loader transaction committed;
there is no second publication pointer or partially visible snapshot.

Keep existing fixed-host, redirect, retry, request and byte limits. Disable environment
proxy inheritance for the Ofwat client's internally constructed HTTP client, matching
the EA clients. The outer deadline bounds the entire job, including source pacing.

Do not add migration 0007 or a refresh audit table yet. Accepted snapshot/retrieval
records already provide durable content provenance; scheduler-retained JSON logs
provide run IDs, phases, failures and outcomes. This deliberately does not provide
a durable queryable failed-run history, last-attempt API, or last-success time for
unchanged static content. Add an append-only audit table when an operational consumer
needs those capabilities, with a separate least-privilege design.

## Consequences

No embedded scheduler, new service, database grants or schema revision are needed.
Operators must configure cadence, age limits, log retention, retries and alerting.
Advisory locks coordinate this entry point, not arbitrary legacy fetch scripts.
Forced termination near commit can leave an uncertain outcome: retry the same evidence
and let loader integrity checks establish whether it already exists. Source status is
accepted local evidence, not publisher availability, current upstream content, or a
guarantee of observation quality. No geometry or publisher relationship policies change.

See the [operations guide](../guides/source-operations.md) for contracts and examples.
