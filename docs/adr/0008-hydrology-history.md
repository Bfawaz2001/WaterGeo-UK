# 0008: Bounded Environment Agency hydrology history

- Status: accepted
- Date: 2026-09-19
- Scope: bounded historical river level/flow readings for one reviewed measure

## Source and purpose

Use the official Environment Agency Hydrology API historical readings endpoint:

`/hydrology/id/measures/{measure_id}/readings`

Hydrology is the Environment Agency's long-term quality-checked archive and
complements the near-real-time Flood Monitoring API. This PR continues using the
same reviewed Hydrology source, licence and publisher identities established in
ADR 0007.

Historical readings are a different evidence product from the latest-observation
snapshot. A historical retrieval has its own requested interval, retrieval window,
content identity and correction/refetch lifecycle. Historical data must therefore
not be appended to `hydrology_latest_observation`.

## Reviewed source behavior

Research on 2026-09-19 confirmed the measure-history endpoint accepts exact
date-time filtering with:

- `mineq-dateTime`
- `maxeq-dateTime`
- `dateTime`

and supports `_limit` and `_sort=dateTime`.

A representative active 15-minute level measure returned 3,041 records across a
31-day candidate interval, ordered by `dateTime`, with 3,041 unique timestamps and
no duplicates.

Separate research confirmed historical missing-quality readings may omit the
`value` member entirely. Such a reading remains an observation and must not be
discarded or converted to zero.

Observed duplicate-free samples support using timestamp as the within-retrieval
reading key for this implementation. They do not establish that publisher history
is globally immutable or that the same measure/timestamp can never change between
later retrievals.

## Retrieval boundary

Each retrieval targets exactly one reviewed publisher measure identity.

The requested interval must:

- contain timezone-aware instants at the WaterGeo API/adapter boundary;
- have `from <= to`;
- span no more than 31 days.

The source request uses inclusive `mineq-dateTime` and `maxeq-dateTime` bounds,
sorted by `dateTime`.

The 31-day limit is a WaterGeo operational bound, not a publisher limit. It keeps a
single retrieval small and predictable while covering approximately one month of
typical 15-minute observations.

Unbounded historical retrieval is not allowed.

## Observation semantics

Every returned reading must reference the requested measure.

Normalize `dateTime` using the Environment Agency GMT contract already accepted in
ADR 0007 and expose aware UTC.

Preserve the complete original reading in `source_fields`.

A numeric value:

- may be negative;
- may be zero;
- must be finite;
- must not have quality `Missing`.

An absent or null value is accepted only when quality is exactly `Missing`.

Do not manufacture values or silently discard missing-quality observations.

Duplicate timestamps within one retrieval fail the complete retrieval rather than
selecting one arbitrarily.

## Persistence model

Use a separate append-only history retrieval table and observation table.

A history retrieval records:

- publisher measure identity;
- requested from/to interval;
- retrieval start/completion timestamps;
- raw content SHA-256;
- normalized SHA-256;
- normalization version;
- record count;
- evidence manifest.

Historical observations are scoped to that retrieval and preserve:

- retrieval ID;
- measure ID;
- observed timestamp;
- nullable numeric value;
- original source fields.

The within-retrieval database identity is `(retrieval_id, observed_at)`.

Do not foreign-key a historical retrieval to a particular hydrology metadata
snapshot row. Metadata snapshots are retrieval-scoped evidence, while the
publisher measure identity is the stable cross-retrieval reference.

## Refetches and corrections

Environment Agency historical data may be corrected after publication.

Therefore:

- exact same evidence and normalization version returns the existing retrieval only
  after stored-content verification;
- changed evidence for the same measure and requested interval creates a new
  retrieval;
- older retrievals remain unchanged;
- ingestion does not UPDATE or DELETE historical evidence.

No automatic canonical merge across overlapping retrievals is introduced in this
PR.

This avoids silently replacing historical evidence or hiding corrections.

## Public API selection

The first public history API exposes one explicit stored retrieval at a time.

A retrieval response includes its provenance and paginated observations.

Ordering is:

1. `observed_at ASC`

Because duplicate timestamps are rejected within a retrieval, that timestamp is a
stable keyset cursor for the retrieval.

Do not expose all history nested under station detail.

Automatic stitching or newest-wins selection across overlapping retrievals is
deferred until correction and overlap semantics have further evidence.

## Retrieval safety

Use only the fixed official Environment Agency HTTPS host and reviewed measure
history path.

Retain the existing protections established in ADR 0007:

- no redirects;
- no environment proxy inheritance;
- connect/read timeouts;
- bounded retries;
- JSON content-type validation;
- response byte budget;
- page/record budget;
- raw response SHA-256;
- ignored local raw evidence;
- completion manifest only after complete retrieval;
- no live Environment Agency dependency in CI.

Validate source metadata publisher, OGL v3 licence and supported API version.

## Database privileges

Historical ingestion is append-only.

Runtime receives SELECT only.

Ingestion receives only the minimum SELECT/INSERT privileges required for history
retrieval and observation tables.

Do not grant UPDATE, DELETE, TRUNCATE, schema CREATE or future blanket privileges.

## Scope exclusions

This decision does not add:

- catchments;
- scheduled refresh;
- freshness alerts;
- automatic historical overlap stitching;
- Flood Monitoring ingestion;
- water quality;
- frontend;
- SDK;
- hosting;
- authentication;
- unrestricted bulk history export.

Those remain separate work.
