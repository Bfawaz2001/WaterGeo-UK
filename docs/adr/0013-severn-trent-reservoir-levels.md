# ADR 0013: Severn Trent Water reservoir levels from Stream

Status: Accepted

Date: 2026-09-23

## Context

Phase 4 needs a first public water-company/industry slice that adds developer value
without creating a collection of undocumented scrapers. The
[source comparison](../data-sources/stream-company-source-assessment.md) found public
Stream ArcGIS services with item-specific licensing and uneven geometry/data contracts.

Severn Trent Water's 2025 raw-water reservoir-level item is public, query-only,
explicitly CC BY 4.0, small enough for complete bounded retrieval and retains stable
reservoir IDs across weekly dated readings. Its point geometry and 2025 edition are
cleanly defined. Southern Water sewer catchments are deferred because 13 of 376
publisher-service WGS84 outputs were invalid; no generic repair policy is justified.

## Decision

Accept only Stream item `0bbd0dd0487346a893d4d615aad9d289` and its exact public
Feature Service/layer. Fix both ArcGIS hosts and paths in code. Reject redirects,
environment proxies, credentials and user-controlled URLs. Retrieve item metadata,
layer metadata, the publisher object-ID set, bounded pages, a second ID set and final
item metadata. Fail if the IDs or item modification identity change during retrieval.

Retain every exact response and write a completion manifest only after strict
normalization. Bound retries, response time, responses, pages, records and bytes.
Re-read and independently verify paths, URLs, headers, sizes, hashes, counts, scope,
content hash and normalized hash before publication.

Use publisher `RESERVOIR_ID` as reservoir identity and (`RESERVOIR_ID`, exact `DATE`
timestamp) as reading identity. The layer declares UTC, while summer values occur at
23:00 UTC on the prior calendar day; preserve the exact aware instant without inventing
a local date. Retain ArcGIS `FID` for evidence verification only. Record the native
EPSG:3857 layer contract and request publisher-generated GeoJSON in EPSG:4326. Validate
that GeoJSON points exactly agree with the published longitude/latitude fields.

Persist immutable snapshots, reservoirs and readings in migration 0009. Store WGS84
points without inferring reservoir footprints. The application role receives SELECT;
ingestion receives SELECT and INSERT only. Exact-content retries reconstruct and hash
all stored records. Changed evidence creates another snapshot.

Expose a Severn Trent-specific `/v1/severn-trent/reservoir-levels` surface with dataset,
reservoir list/detail, nearby search and snapshot-pinned reading pagination. Preserve
publisher facts and caveats. Do not calculate drought/supply status, interpolate,
convert units or assert links to WaterGeo's Ofwat/EA data.

Treat the 2025 edition as static/versioned for source status. Add manual bounded refresh
support without a scheduler. A later year or a materially changed item requires review
and a new normalization contract rather than silent widening.

## Consequences

WaterGeo gains a complete, reproducible company operational-data slice and a concrete
pattern for licensed Stream Feature Services. It does not yet provide current reservoir
conditions, national reservoir coverage, physical reservoir polygons or cross-company
comparability. Capacity meanings can differ across companies. Source values must not be
used by WaterGeo to announce restrictions or safety conditions.
