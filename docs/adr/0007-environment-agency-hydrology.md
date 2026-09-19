# 0007: Environment Agency hydrology snapshots

- Status: accepted
- Date: 2026-09-19
- Scope: station metadata, measures and latest available river level/flow readings

## Evidence and source choice

Select the official Hydrology API for its measure semantics, quality flags and
future history support. Flood Monitoring is an alternative for fresher telemetry,
but its actual responses contain ambiguities needing separate review.
The [source assessment](../data-sources/environment-agency-hydrology.md) records
current official references, explicit OGL v3, attribution, England coverage and
observed API 2.1.1. This is not a UK-wide or guaranteed real-time service.

The [timed verification](../data-sources/environment-agency-hydrology-verification.json)
retrieved 2,982 stations, 12,326 measures and 12,243 latest observations in three
pages. All identities, relationships, embedded measure references and normalized
values passed validation. These are dated observations, not permanent invariants.

## Identity and missing locations

Preserve station notation and URI; a stationGuid alone is not unique for composite
publisher identities. Preserve each measure notation/URI and station relationship,
parameter, unit, period and original semantic fields. Do not merge similar labels.
A reading belongs to a measure and observation timestamp. This slice has at most
one latest observation per measure per snapshot; duplicate latest identities fail.

Banks Road lacks coordinates in both official list and detail responses. The
maintainer explicitly approved retaining legitimate absent locations. Store both
coordinates and geometry as NULL, expose `location_status: unavailable`, retain
all measures/readings and keep detail accessible. Never infer or geocode location.
The policy applies to all legitimately absent locations, not one hard-coded ID.

Partial pairs, invalid types, non-finite values and out-of-range WGS84 coordinates
reject the complete snapshot. Latitude/longitude are authoritative WGS84. Preserve
BNG fields; require their complete finite numeric pair if supplied. A BNG-only
record requires new assessment. No cross-CRS equality tolerance or positional
accuracy claim is introduced. Database constraints enforce coordinate/geometry
nullness, ranges, nonempty valid Point geometry and exact coordinate agreement.

Expose station count, with-location count and without-location count. Reject a new
publication if the located fraction drops by more than one percentage point from
the latest compatible stored snapshot, requiring source review. This is a change-
detection guard, not a claim that smaller changes are harmless. Review first-load
counts and later source changes against the dated evidence; do not force fixed counts.

## Dynamic snapshots, evidence and atomic ingestion

Migration `0004` adds four tables independent of Ofwat: `hydrology_snapshot`,
`hydrology_station`, `hydrology_measure`, `hydrology_latest_observation`.
Snapshot-scoped publisher keys and foreign keys preserve relationships. Original
source fields remain alongside queryable columns; station status and reading
quality/completeness remain distinct. Null-valued `Missing` readings, measures
without any latest reading and numeric zero are different states.

The fetcher saves exact JSON response bytes after HTTP content decoding beneath
ignored data/raw. Its completion manifest records request URLs, request/retrieval
start and completion times, page counts, byte counts, SHA-256 hashes and available
Date/ETag/Last-Modified/Content-Type headers. Missing headers are not manufactured.
No completion manifest is written for incomplete retrieval.

The content SHA-256 hashes a canonical JSON array of each page's kind, request URL
and response SHA-256. Retrieval times/headers are deliberately excluded from content
identity. A separate normalized hash includes `ea-hydrology-river-v1` and sorted
normalized records, including preserved source fields. The loader rechecks raw
hashes, pagination and source contracts before any database insertion.

A complete snapshot is inserted in one transaction under the SELECT/INSERT-only
ingestion role. Failure rolls everything back. An advisory transaction lock
serializes publication/retry decisions. The same exact content and normalization
version returns the existing snapshot only after normalized-hash, row-count and
actual stored child-content verification. A separate recomputed digest covers every
normalized station/measure/observation field, preserved source_fields, labels and
fixed-little-endian EWKB geometry including SRID. Rows use C-collated publisher ID
order; queryable float8 values use exact binary representations, timestamps use UTC
microseconds, and JSONB is parsed with exact decimal numbers and canonical key/value
ordering (numeric scale is immaterial; booleans remain distinct). This verification
digest does not change snapshot identity, content_sha256 or normalization version.
A mismatch raises HydrologyError without replacing or repairing any stored row;
it does not advance its retrieval time. Source corrections produce another snapshot.
Newest retrieval completion time, then UUID, selects the default compatible snapshot.
Independent source pages are not an immutable or publisher-atomic release.

Offset-free observation times explicitly use the official Hydrology GMT contract;
normalize to aware UTC and preserve original dateTime. Reject unsupported precision
beyond microseconds rather than truncating timestamps. Expose retrieval and
observation timestamps separately. Latest may be decades old: no invented freshness
status and no “live” label. Historical series are outside this implementation.

## Retrieval bounds and failure behavior

Use the locked `httpx2` stack with fixed official HTTPS paths, one request in flight,
10-second connect and 60-second read timeouts, at most three attempts on transport
failures/429/transient 5xx, short bounded backoff, no environment proxy configuration,
and WaterGeo UK User-Agent. Reject all redirects and non-JSON content. Publisher
HTTP identity URIs are stored identifiers, never caller-controlled fetch targets.

Request 30,000 rows per page, obey the effective response limit and offset, and
require a terminal short page. Station/measure requests sort by notation; latest
readings use the documented source filter. Bound each family to 20 pages/100,000
records, each decoded page to 32 MiB and the full retrieval to 256 MiB. Check elapsed
body-stream time as well as socket timeouts. Reject missing/duplicate IDs, loops,
invalid metadata, unsupported API version/licence and cross-reference mismatches.
An incompatible API change requires a new assessment, not an automatic upgrade.

These checks cannot establish cross-request transactional consistency in a changing
publisher API. Retrieval-window provenance makes that limitation explicit. There
is no live public-source dependency in CI.

## Read-only API and nearby search

- `GET /v1/hydrology/dataset`
- `GET /v1/hydrology/stations`
- `GET /v1/hydrology/stations/near?lon=&lat=&radius_m=&limit=`
- `GET /v1/hydrology/stations/{station_id}`

Lists default to 50 and cap at 100 summaries. Continue with `next_after_id` as
`after_id` and the returned `snapshot_id` to keep pagination stable across later
loads. Detail is bounded to 64 measures, with one latest reading each; excessive
source nesting fails normalization rather than silently truncating. Optional source
metadata, qualifiers, statistic and quality flags are retained in `source_fields`.

Store located stations as `geometry(Point,4326)`. A partial GiST geography-expression
index supports `ST_DWithin`; use WGS84 spheroidal geography distances in metres,
ordered by distance ascending then station ID under C collation. Radius defaults
to 10 km and caps at 100 km; result limit caps at 100. Null geometries are excluded
and the response explicitly explains the exclusion and reports dataset completeness.
Finite coordinate/range checks and parameterized SQL apply throughout. Existing
three-second statement timeout remains. Unknown stations return 404; missing or
incompatible datasets/database failures return a sanitized 503. Responses use no-store.

Runtime receives SELECT only on the four new tables. Ingestion receives only
SELECT/INSERT, with no UPDATE, DELETE, TRUNCATE, schema CREATE or future blanket
grants. No Ofwat canonical/presentation policy, table or provenance changes occur.

## Verification and follow-ups

Synthetic tests cover source validation, paging, retries, tampering and API inputs.
Disposable PostGIS tests cover migration round trips, geometry/null constraints,
atomic rollback, foreign keys, exact-content retry, list/detail/near, distance tie
ordering, spatial completeness degradation and actual privilege denial.

The real-source run loaded and verified an exact-content retry in disposable
PostGIS, then checked all 2,982 station detail HTTP outputs, all measure/observation
counts, list pagination, Banks Road detail and bounded distance ordering. Its small
summary records runtime, coordinate bounds, timestamp range, optional/null fields
and provenance. Bulk payloads remain ignored locally.

Follow-ups: bounded historical queries (PR #15), catchment relationships (PR #16),
then scheduling, freshness monitoring and hardening (PR #17), subject to evidence.
History requires explicit correction/replacement semantics: latest-value snapshots
do not reconstruct a complete series. Phase 3 concerns water quality. No frontend,
deployment, authentication, flood alerts or bulk export is included here.
