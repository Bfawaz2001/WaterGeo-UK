# ADR 0009: Environment Agency Catchment Data Explorer Cycle 3 hierarchy

- Status: Accepted
- Date: 2026-09-19

## Context

WaterGeo UK already exposes reviewed Environment Agency Hydrology stations, measures,
latest observations, and bounded historical observations. Phase 2C adds catchment context.

The Hydrology API must not be treated as if it publishes station-to-catchment assignments.
Reviewed station responses did not expose a usable `sampleOf` catchment relationship, and
the reviewed station population did not provide identified catchment entities. Some
stations expose a `catchmentArea` value, but that is an attribute rather than a publisher
identity or hierarchy relationship.

The Environment Agency Catchment Data Explorer (CDE) is a separate public source. Its
Cycle 3 pages expose an explicit publisher hierarchy:

`River Basin District -> Management Catchment -> Operational Catchment -> Water Body`

Reviewed examples confirmed both downward and upward links. For example, Cycle 3
Operational Catchment `3471` links to Management Catchment `3101`, River Basin District
`4`, and its Water Bodies; Water Body `GB104028047290` links back to those same parents.

The reviewed Cycle 3 traversal also identified 10 River Basin Districts, 117 Management
Catchments, and 750 Operational Catchments before the service began returning temporary
HTTP 403 responses during rapid crawling. A later single request to one of those blocked
Operational Catchments returned HTTP 200, so the incomplete Water Body count from that
crawl is not accepted as source evidence.

CDE responses reviewed during this work did not expose `ETag` or `Last-Modified`
validators. The publisher also exposes unversioned pages alongside versioned Cycle 3
pages. WaterGeo therefore needs to retain the explicit plan version and the retrieval
evidence instead of treating the current unversioned hierarchy as timeless.

CDE GeoJSON also needs precise semantics. A Water Body GeoJSON response can contain
multiple publisher geometry features for one Water Body. For reviewed Water Body
`GB104028047290`, the response contained a `Catchment` Polygon and a `RiverLine`
MultiLineString. Parent-level GeoJSON responses can contain constituent Water Body
features rather than one canonical polygon whose identity is the parent catchment.

## Decision

Phase 2C will ingest the Environment Agency Catchment Data Explorer Cycle 3 hierarchy as
an independent, provenance-preserving snapshot.

The source plan identifier is fixed to `c3-plan` for this phase.

The normalized hierarchy is:

1. River Basin District
2. Management Catchment
3. Operational Catchment
4. Water Body

Parent-child relationships are accepted only when they are directly exposed by publisher
links in the reviewed Cycle 3 source. WaterGeo will not infer hierarchy relationships from
spatial containment or from names.

The snapshot stores publisher identifiers, names, publisher URIs, parent identities, and
source fields. Cross-level foreign keys preserve the complete publisher chain and fail
closed when a child references a parent not present in the same accepted snapshot.

Water Body geometry is stored separately from hierarchy entities. Each source GeoJSON
feature retains its feature order, publisher geometry-type URI, derived short geometry
kind, WGS84 PostGIS geometry, and source properties. The schema does not assume there can
be only one geometry feature of each kind for a Water Body.

WaterGeo will not dissolve constituent Water Body polygons into Management Catchment,
Operational Catchment, or River Basin District polygons in this phase. If derived parent
geometry is added later, it must be explicitly labelled as WaterGeo-derived rather than
publisher geometry.

The retrieval is snapshot-oriented and append-only. A completed evidence bundle has
retrieval timestamps, raw content hashes, a normalized hash, normalization version,
entity/geometry counts, and a manifest. Only a completed validated bundle may be loaded.

An exact-content retry may return an existing snapshot only after the stored normalized
header and child content have been verified against the accepted evidence. Changed source
content creates a new snapshot. Ingestion does not update or delete accepted snapshots.

## Retrieval and service protection

CDE hierarchy traversal uses the official
`https://environment.data.gov.uk/catchment-planning/` host and the versioned
`/v/c3-plan/` paths.

The client must:

- use HTTPS and the fixed official host;
- disable environment proxy inheritance;
- refuse redirects;
- use bounded connect/read/write/pool timeouts;
- use bounded retries, response bytes, records, and traversal depth;
- traverse publisher hierarchy links only;
- keep hierarchy traversal sequential;
- use deliberately conservative sequential retrieval. The current Data Services
  Platform guidance distinguishes automated/system-to-system services (up to 200
  requests per minute) from web bots/crawlers/scrapers (up to 10 requests per
  minute). WaterGeo uses a one-second minimum interval (at most 60 requests per
  minute), below the automated-service ceiling;
- treat HTTP 403/429 or other incomplete traversal as a failed retrieval, never as an
  empty child set;
- retain raw evidence and request URLs with hashes;
- write the completion manifest only after the full source contract has validated.

Incomplete retrieval directories may remain as raw diagnostic evidence but are not
loadable.

## Database model

Migration `0006` adds:

- `watergeo.catchment_snapshot`
- `watergeo.catchment_river_basin_district`
- `watergeo.catchment_management`
- `watergeo.catchment_operational`
- `watergeo.catchment_water_body`
- `watergeo.catchment_water_body_geometry`

The application role receives `SELECT` only.

The ingestion role receives `SELECT` and `INSERT` only. It does not receive `UPDATE`,
`DELETE`, `TRUNCATE`, schema creation, or other mutation privileges.

The application schema revision becomes `0006`.

## Public API direction

The initial public API will expose the accepted hierarchy by explicit snapshot/current
dataset semantics established during implementation. It may provide hierarchy navigation
and Water Body geometry.

The API must not imply a Hydrology station-to-catchment assignment unless a separate
publisher-supported relationship is reviewed and added later.

Any geometry returned from `catchment_water_body_geometry` must preserve whether it is a
publisher `Catchment`, `RiverLine`, or another reviewed publisher geometry kind.

## Reviewed real-source verification

A complete Cycle 3 retrieval was reviewed on 20 September 2026. The accepted
evidence bundle contained 888 publisher responses and normalized to:

- 10 River Basin Districts;
- 117 Management Catchments;
- 750 Operational Catchments;
- 4,929 Water Bodies; and
- 8,701 Water Body geometry features.

The evidence bundle had content SHA-256
`2c9b9b1b64da999da1f422fc06ae765218ef645b9d3db7a9ea6550ad87e822c7`
and normalized SHA-256
`dba65d6305a5bc19057d34effafae21418275346da8142d7958d0274fe4b70ad`.

The complete bundle was re-read and normalized before publication to a disposable
PostGIS database. The first load inserted one snapshot and an exact-content retry
returned the same snapshot only after recomputing integrity from the stored
hierarchy rows and PostGIS geometries. Stored child counts matched the normalized
counts exactly.

The reviewed source exposed publisher Water Body geometry kinds `Catchment` and
`RiverLine`, represented by Polygon, MultiPolygon, LineString and MultiLineString
GeoJSON geometries. Parent-level GeoJSON remains treated as collections of
constituent Water Body features rather than publisher-authored canonical parent
polygons.

This verification does not create or imply a publisher Hydrology
station-to-catchment relationship. Any later spatial association must be represented
separately as a WaterGeo-derived relationship.

## Consequences

WaterGeo gains an authoritative Environment Agency catchment hierarchy without presenting
spatial inference as publisher fact.

The model is more verbose than storing only names or dissolved polygons, but it preserves
publisher identity, plan version, hierarchy, and geometry provenance.

Snapshotting permits later publisher changes or future river basin planning cycles to
coexist without mutating Cycle 3 evidence.

Full retrieval is intentionally slower because the public service must be traversed
politely and fail closed when throttled. Completeness is preferred over silently accepting
partial hierarchy data.

## Out of scope

This phase does not:

- assign Hydrology stations or measures to Catchment Data Explorer entities;
- infer station relationships by point-in-polygon;
- derive or dissolve parent-level catchment geometry;
- merge Cycle 2 and Cycle 3 identities;
- treat unversioned CDE pages as timeless canonical state;
- ingest classifications, objectives, reasons for not achieving good status, measures,
  investigations, protected areas, or summary statistics;
- add scheduled refresh/freshness automation.