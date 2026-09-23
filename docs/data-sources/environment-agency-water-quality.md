# Environment Agency Water Quality Explorer source assessment

Reviewed: 2026-09-21. Status: sampling-point source contract implemented and
verified against a complete live retrieval. Database ingestion and public WaterGeo
API are deliberately deferred until the source model has been reviewed.

## Official source and selected scope

Publisher: Environment Agency (EA).

Public service root:

`https://environment.data.gov.uk/water-quality`

Public API documentation:

`https://environment.data.gov.uk/water-quality/api-docs`

The reviewed OpenAPI document is available from:

`https://environment.data.gov.uk/water-quality/api/swagger`

At review time the OpenAPI document reported version 3.1.0, service title
`Water Quality Archive`, service version `1.3.1`, and the production server root
above.

Phase 3A is intentionally limited to sampling-point metadata. Samples,
samplings, observations, determinands, units and other codelists remain outside
this first slice.

## Licence

The Water Quality Explorer site states that its content is available under the
Open Government Licence version 3. Preserve publisher attribution and OGL v3
separately from WaterGeo's MIT code licence.

## Sampling-point contract

The reviewed collection endpoint is:

`POST /water-quality/data/sampling-point`

A normal unfiltered collection request requires JSON body `null`. Sending an
empty JSON object is not equivalent: the API attempts to validate it as a
GeoJSON Polygon or MultiPolygon and returns HTTP 422.

WaterGeo requests:

- `Accept: application/ld+json`
- `Content-Type: application/json`
- `Accept-Crs: http://www.opengis.net/def/crs/EPSG/0/4326`
- `API-Version: 1`

The endpoint supports `skip` and `limit` query pagination. The reviewed live
OpenAPI contract caps JSON-LD pages at 250 records, with a default of 100.
WaterGeo uses 250.

The endpoint also accepts optional point, radius, administrative-area, status,
type and GeoJSON Polygon/MultiPolygon filters. Phase 3A does not generalise those
filters into the WaterGeo public API.

The default publisher representation is BNG. WaterGeo explicitly asks for
EPSG:4326 rather than assuming or transforming the default response.

Successful reviewed responses returned:

- HTTP 200
- `Content-Type: application/ld+json`
- `Content-Crs: http://www.opengis.net/def/crs/EPSG/0/4326`
- `API-Version: 1`
- `X-Total-Items`
- `X-Page-Skip`
- `X-Page-Limit`

The JSON-LD collection contains `@context`, `@type`, `totalItems`, `view`, and
`member`. Pagination links in the reviewed Hydra `view` are publisher metadata;
WaterGeo constructs only its own fixed-host bounded requests and does not follow
arbitrary response URLs.

## Identity and notation semantics

Each sampling point exposes a publisher `id` URI and `notation`.

The notation is treated as an opaque publisher identifier. WaterGeo preserves it
exactly and requires it to equal the suffix of the reviewed publisher identity
URI.

The complete 2026-09-21 snapshot contained 66,300 unique notations. Forty-two
notations contained at least one space, with 44 space characters in total, and
four notations contained `/`. Reviewed examples include:

- `AN-B BOOTH`
- `AN-CORBY  I`
- `MD-GWW20/01`
- `NW-GWW08/02`

These characters are valid publisher data and must not be trimmed, replaced,
URL-normalised or rewritten into a synthetic key.

The longest reviewed notation was 11 characters. WaterGeo nevertheless keeps a
bounded identifier contract rather than hard-coding that observed maximum.

## Labels, concepts and source structure

The reviewed sampling-point model contains:

- publisher identity and notation;
- `altLabel` and `prefLabel`;
- an observations relationship;
- WGS84 point geometry when explicitly requested;
- sampling-point status;
- sampling-point type;
- region;
- area; and
- sub-area.

All 66,300 records in the reviewed snapshot had the same source-field shape and
none of the reviewed fields above were null.

The snapshot contained two statuses:

- `O` / `OPEN`: 38,881
- `C` / `CLOSED`: 27,419

There were 99 distinct sampling-point types. The largest reviewed categories
included freshwater rivers (`F6`, 18,445), non-water-company treated sewage
effluent (`UA`, 7,720), and water-company treated sewage effluent (`SA`, 5,721).

The source exposed 7 regions, 18 areas and 88 sub-areas in the reviewed
snapshot. The OpenAPI description warns that region, area and sub-area fields
may be discontinued. WaterGeo therefore preserves them as source metadata and
must not make their continued publication a permanent identity assumption.

## Geometry

The reviewed JSON-LD representation expresses a sampling-point geometry as
GeoSPARQL WKT, for example:

`POINT(-1.192 52.0473) <http://www.opengis.net/def/crs/EPSG/0/4326>`

Phase 3A accepts only reviewed WGS84 Point geometry from this representation.
It does not reinterpret other WKT types or silently transform another CRS.

All 66,300 reviewed sampling points supplied locations.

Observed coordinate bounds were:

- longitude: -6.354 to 1.7965
- latitude: 49.8896 to 56.02

These bounds describe this retrieval only. They are not a claim that WaterGeo or
the source is a complete UK monitoring network.

## Retrieval, service protection and completeness

WaterGeo uses a fixed HTTPS host, disables environment proxy inheritance,
refuses redirects, applies bounded retries and timeouts, and validates response
content type, CRS and API version.

A complete retrieval is bounded by page, byte and record budgets. A completion
manifest is written only after every expected record has been retrieved.

The client deliberately spaces publisher requests by at least 0.5 seconds. This
keeps the sequential retrieval below the Data Services Platform automated-use
ceiling reviewed during implementation while avoiding an unnecessary burst of
requests.

The reviewed complete retrieval used 266 sequential responses: 265 full
250-record pages and one final 50-record page. Every page reported the same
66,300-record total.

A changed `totalItems`, duplicate publisher identity, incomplete page,
unexpected response contract, invalid coordinate, non-finite JSON value or
partial traversal rejects the snapshot rather than silently accepting it.

## Evidence retention and verification

Raw responses and the completion manifest are retained locally beneath ignored:

`data/raw/environment-agency/water-quality/sampling-points/`

The reviewed bundle was retrieved from
2026-09-21T00:13:05.244589+00:00 to
2026-09-21T00:15:22.334466+00:00.

It contained:

- 66,300 sampling points;
- 66,300 sampling points with locations;
- 0 sampling points without locations;
- 266 response pages;
- 82,405,025 raw response bytes.

Content SHA-256:

`2c5da92d010430a078e4c7aa40318aeb46de4e56a1a15e69fb84859917bc11c1`

Normalized SHA-256:

`21433969c0803233499c76e336af0e03a9335de6fdd28f44b9ebbaaa1b8c2d9f`

The bundle was re-read from local immutable evidence after retrieval. That
second normalization exposed and then verified the publisher's valid space and
slash notation cases without another network request.

See
[verification evidence](environment-agency-water-quality-verification.json)
and [ADR 0011](../adr/0011-environment-agency-water-quality.md).

## Sampling-point persistence, API and operations

Migration `0007` stores append-only snapshots and WGS84 sampling points. Exact-content
retries verify stored children, and spatial-completeness regressions fail closed.
The public `/v1/water-quality/dataset`, `/sampling-points`, `/sampling-points/near`
and `/sampling-points/{sampling_point_id}` routes support explicit `snapshot_id`.
Listing uses `after_id`, limit 1–100 and C-collated identity ordering. Nearby results
use geography distance then identity, within at most 100 km, excluding missing locations.
Pass spaces and slashes URL-encoded; detail routing preserves them exactly.
Broad lists do not expose raw source fields. Region/area/sub-area are explicitly
publisher metadata, not WaterGeo geographic identities or company relationships.

Refresh with `uv run --locked python scripts/refresh_sources.py water-quality`;
use `--evidence-dir` for a verified offline retry. The existing deadline, safe logs,
source lock (refresh key 5 in namespace 1464296784) and atomic loader apply.
No new scheduled workflow is enabled. Choose metadata cadence through deployment review.

`/v1/sources/status` reports Water Quality retrieval age. Optional
`WATERGEO_WATER_QUALITY_RETRIEVAL_MAX_AGE_SECONDS` uses an explicit operator limit;
unset means unknown. Sampling points have no observation-freshness classification.
The source is mutable metadata, not a static edition or publisher-atomic snapshot.

Actual observation contracts are reviewed separately in the
[bounded observation assessment](environment-agency-water-quality-observations.md).
Sampling-point publication alone does not complete Phase 3.
