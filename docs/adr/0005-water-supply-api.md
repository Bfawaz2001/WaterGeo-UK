# 0005: Public API for the reviewed water-supply snapshot

- Status: accepted
- Date: 2026-09-18
- Builds on: ADR 0002, ADR 0003 and ADR 0004

## Context and decision

Canonical ingestion now preserves the reviewed Ofwat v1.5 archive as 1,141 areas
with five explicit transformation records. Expose that dataset using synchronous
FastAPI routes, typed public models, and a small SQLAlchemy query module. Existing
PostGIS tables, the area GiST index and read-only runtime grants are sufficient.
No migration, additional dependency, generic repository framework or background
ingestion process is required.

The public dataset is selected by the exact archive SHA-256 and transformation
version shared with ingestion in `core/datasets.py`. Do not pick the newest row:
a newer unreviewed or synthetic snapshot must not silently become public. The
loader remains responsible for validating completeness and provenance before its
atomic commit. The API reports observed counts; it does not repeat canonical
hash verification for each HTTP request.

## Routes and public contracts

| Route | Response |
| --- | --- |
| `GET /v1/water-supply/dataset` | `DatasetMetadata`: snapshot identity, release, counts, dates, source URL/hash/size, publisher/distributor, licence, attribution and analytical-use disclaimer. |
| `GET /v1/water-supply/areas` | `AreaPage`: ordered `AreaSummary` items without geometry. |
| `GET /v1/water-supply/areas/at-point?lon=...&lat=...` | The same page shape, filtered by point coverage. |
| `GET /v1/water-supply/areas/{source_id}` | `AreaDetail`: publisher notices and optional `TransformationMetadata`, plus a geometry URL. |
| `GET /v1/water-supply/areas/{source_id}/geometry` | `AreaFeature`: one GeoJSON Feature with MultiPolygon geometry and detail properties. |

Public labels map directly from observed source fields: `AreaServed`, `COMPANY`,
`Acronym`, `CoType`, `AreaType`, `Version`, `LastUpdate`, and `WARNINGS`. They are
publisher descriptions, not reconciled company identities. Detail responses retain
`Licence`, `Provenance`, `Disclaimer`, `Disclaim2`, and `Disclaim3` as named public
properties. Arbitrary source JSON and internal transformation `details` are not
exposed. Reviewed transformations expose algorithm/parameters, library versions,
source/canonical WKB hashes, validity reason, review status/reason/reference and
transformation time. The review reference is a repository-relative ADR path.

Lists link to `/v1/water-supply/dataset` instead of repeating all dataset metadata.
Snapshot UUIDs in responses allow consumers to identify the dataset used. The
licence version remains JSON `null`; no OGL edition is inferred. Public API output
does not change the licensing of the underlying information.

## Pagination and input validation

List and point routes accept `limit` (1–100, default 50) and `after_id` (nonnegative
signed-bigint range, default 0). Read `limit + 1` records to determine whether a
next page exists; return `next_after_id` or `null`. Continue point pagination with
the same coordinates. Ordering is by publisher source ID, scoped to this fixed
snapshot. There is no offset scan or implicit geometry inclusion.

IDs and pagination use unsigned decimal notation; reject decimal/exponent forms,
negative numbers and bigint overflow. Longitude/latitude must be finite and within
[-180,180]/[-90,90]. Unknown query parameters return 422, including `bbox`.
Connections are acquired lazily after input validation, so invalid requests do
not query the database.

Bounding boxes are deferred. A transformed geographic rectangle does not generally
remain a rectangle in British National Grid; exact edge semantics and antimeridian
handling warrant a separate contract. Unsupported bbox parameters fail explicitly
rather than being ignored or accidentally returning the whole dataset.

## Spatial semantics and performance

Point lookup uses [ST_Covers](https://postgis.net/docs/ST_Covers.html), including
points on exterior or hole boundaries. Interior holes do not match. Adjacent,
overlapping and inset areas may produce multiple matches; the API does not choose
a supplier. Points outside all areas return an empty page.

Transform the single WGS84 point into EPSG:27700 and compare with the stored indexed
geometry. The conservative processing extent is longitude -9..3 and latitude
49..61, enclosing the reviewed England/Wales coverage. Valid worldwide coordinates
outside that extent return an empty page without projecting distant coordinates
or poles into British National Grid. This bound is specific to this published
dataset; review it when publishing another source.

Metadata requests use one SQL query; list/point/detail requests use two, and
geometry requests use three. Points outside the processing extent only need the
metadata query. No query count grows with the number of returned areas. The snapshot
lookup uses its unique content/transformation key. Area detail uses the composite primary
key, and spatial filtering leaves the indexed area geometry untransformed.

## GeoJSON output

Use [ST_Transform](https://postgis.net/docs/ST_Transform.html) to reproject the one
requested geometry to EPSG:4326. Orient rings with `ST_ForcePolygonCCW` and serialize
with `ST_AsGeoJSON(..., 15, 0)`: longitude first, no legacy `crs` member, and media
type `application/geo+json`. Canonical EPSG:27700 geometry is never updated.

There is no simplification, snapping or geometry repair on output. Decimal
serialization is necessarily finite precision; PostGIS warns that reducing output
precision can invalidate geometry in its [GeoJSON documentation](https://postgis.net/docs/ST_AsGeoJSON.html).
Reparse and validate the representation before returning it. If it is invalid,
return a generic 503 instead of silently changing the geometry.

Serialized geometry is limited to 8 MiB (properties/envelope add a small overhead).
Oversized geometry returns 413 before transferring the geometry to Python. The
existing three-second statement timeout bounds reprojection/serialization work.
The limit does not avoid allocating the serialized geometry within PostgreSQL.
Coordinate-transform accuracy depends on the installed PROJ database/grids;
centimetre accuracy or identical transformed output across environments is not
promised. Boundary decisions use the resulting projected coordinate without a
distance tolerance, so points extremely close to edges can be sensitive to that
accuracy. Original data caveats also continue to apply.

Local checks against the already ingested 1,141-area snapshot found that IDs
**3, 4, 16 and 21** become self-intersecting after `ST_Transform(..., 4326)`.
Serializing with either 15 or 17 decimal digits retained that invalidity; it is
not just a decimal-output issue. Their GeoJSON route therefore returns 503 in
that environment, while metadata and canonical-CRS spatial lookup remain usable.
This is an observed output limitation, not permission for another repair. Other
PROJ/grid versions may differ. A reviewed presentation transformation is a
specific Phase 1 follow-up before claiming complete WGS84 geometry availability.

## Failures and security

Missing published data and database/query/representation failures return generic
503 responses. An unknown area in a loaded snapshot returns 404. Input failures
return 422. Data responses and explicit data errors use `Cache-Control: no-store`
until cache validators have a defined contract. `/health` and `/ready` keep their
existing meanings; infrastructure readiness does not imply that data is loaded.

All caller values are bound SQL parameters. SQL composition joins only fixed
developer-owned fragments. The runtime uses `watergeo_app`; privileges and all
connection/pool/statement/lock timeouts stay intact. No arbitrary URL retrieval,
filesystem access or write endpoint is introduced. Failure logging records the
exception class, not database messages, SQL values or credentials.

The API is usable locally; internet hosting still needs the deployment controls
described in SECURITY.md, including request/rate limits and monitoring.

## Verification and remaining Phase 1 work

Unit tests cover invalid IDs/pagination/coordinates/unknown parameters, failure
sanitisation, missing data and OpenAPI. Disposable PostGIS tests exercise actual
HTTP routing, source mappings, metadata, pagination, shared edges/overlaps/holes,
WGS84 output, ring orientation, unchanged canonical WKB, bounded output and query
count. Tests use synthetic shapes only and the real read-only runtime role.

A read-only local smoke check of the existing real load confirmed 1,141 areas,
five transformations, an unidentified licence edition, list/detail/point responses,
and successful GeoJSON for IDs 1, 6, 28 and 30. The full point-query EXPLAIN used
`water_supply_area_geom_idx`. The tiny CI fixture checks index eligibility for
the same spatial predicate in isolation; its complete ordered query may reasonably
prefer the primary key. Local real-data checks are separate from CI and do not
download or write publisher records.

Next: Phase 1 completion work, including a reproducible end-to-end developer
walkthrough, presentation of transform precision/limits, and deployment readiness
before a hosted service. Dataset switching, bbox queries and bulk geometry export
need explicit contracts if added. Environment Agency integration remains Phase 2.
