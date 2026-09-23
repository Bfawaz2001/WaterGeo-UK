# ADR 0011: Environment Agency Water Quality Explorer sampling points

- Status: Accepted
- Date: 2026-09-21

## Context

WaterGeo UK has completed reviewed water-supply boundaries and Environment
Agency Hydrology/catchment source integration. Phase 3 introduces water-quality
data.

The Environment Agency Water Quality Explorer is the current public service
reviewed for this work. Its production root is:

`https://environment.data.gov.uk/water-quality`

The service publishes sampling points, samples, samplings, observations and
supporting codelists. Integrating all of those contracts at once would make it
difficult to distinguish publisher semantics from WaterGeo assumptions.

Phase 3A therefore establishes the sampling-point contract first.

The live OpenAPI document reported OpenAPI 3.1.0, service version 1.3.1 and
`API-Version: 1`.

A significant source detail discovered during review is that the collection
endpoint is not a conventional GET endpoint. The reviewed endpoint is:

`POST /data/sampling-point`

Its optional request body is a GeoJSON Polygon/MultiPolygon or null. An
unfiltered request must send JSON `null`; `{}` fails validation.

The endpoint defaults to British National Grid. WaterGeo explicitly requests
EPSG:4326 for the reviewed sampling-point evidence.

## Decision

Phase 3A will implement bounded, provenance-preserving retrieval and strict
normalization of Environment Agency Water Quality Explorer sampling points.

No database schema or public WaterGeo endpoint is introduced by this ADR.
Persistence follows only after the complete source population has been reviewed.

The source contract is fixed to:

- HTTPS host `environment.data.gov.uk`;
- service root `/water-quality`;
- `POST /data/sampling-point`;
- JSON request body `null` for the unfiltered snapshot;
- `Accept: application/ld+json`;
- `Accept-Crs: http://www.opengis.net/def/crs/EPSG/0/4326`;
- `API-Version: 1`;
- `limit=250`; and
- offset pagination using `skip`.

WaterGeo does not follow arbitrary publisher pagination URLs. It constructs
bounded requests against the reviewed fixed host and path.

## Publisher identity

Sampling-point `notation` is an opaque publisher identifier.

WaterGeo preserves the notation exactly and verifies that it matches the suffix
of the sampling-point publisher URI. It must not trim, slugify, URL-encode,
replace or otherwise canonicalise valid publisher characters.

The complete reviewed snapshot proved that an alphanumeric-and-hyphen-only
contract would be incorrect. Of 66,300 unique notations:

- 42 contained at least one space;
- those identifiers contained 44 spaces in total; and
- 4 contained `/`.

Examples include `AN-B BOOTH`, `AN-CORBY  I`, `MD-GWW20/01` and
`NW-GWW08/02`.

The client therefore accepts the reviewed bounded notation character set while
still rejecting query, fragment, encoded-delimiter and control characters.

Duplicate publisher identities reject the snapshot.

## Geometry

WaterGeo asks the publisher to return EPSG:4326.

The reviewed JSON-LD source represents geometry as GeoSPARQL WKT such as:

`POINT(-1.192 52.0473) <http://www.opengis.net/def/crs/EPSG/0/4326>`

Phase 3A accepts only a finite WGS84 Point under that reviewed contract.
Unsupported geometry kinds, another CRS, malformed WKT, partial coordinates or
out-of-range coordinates fail closed.

Missing geometry is represented explicitly as an unlocated sampling point rather
than being invented. The complete reviewed population happened to contain
locations for all 66,300 points; this observed count is not hard-coded as a
permanent publisher guarantee.

No coordinate transformation is performed in this phase.

## Source metadata

WaterGeo preserves:

- publisher URI and notation;
- alternative and preferred labels;
- the observations relationship;
- sampling-point status;
- sampling-point type;
- region;
- area;
- sub-area; and
- original source fields.

Region, area and sub-area are publisher metadata rather than WaterGeo geography.
The OpenAPI contract warns that these fields may be discontinued. They must not
be used as permanent identity components.

The reviewed snapshot contained 2 statuses, 99 sampling-point types, 7 regions,
18 areas and 88 sub-areas.

## Retrieval and evidence

Retrieval uses an immutable local evidence bundle.

Each raw response is stored before normalization. The completion manifest
contains retrieval timestamps, request URLs, allowlisted response headers,
response hashes, page counts and the aggregate content hash.

The completion manifest is written only after the complete expected population
has been retrieved.

The reader independently revalidates:

- fixed request identity;
- evidence file identity and hashes;
- byte and page budgets;
- page sizes;
- reported totals;
- terminal pagination;
- duplicate publisher identities;
- source collection contract;
- retrieval timestamps; and
- normalized content.

Incomplete retrieval directories may remain for diagnosis but are not accepted
as completed evidence.

## Service protection

The retrieval remains sequential.

WaterGeo enforces a 0.5-second minimum interval between publisher requests. That
is deliberately below the automated-use request ceiling reviewed from the
Environment Agency Data Services Platform during implementation.

Retries are bounded and restricted to transport failures, HTTP 429 and selected
transient 5xx responses.

Redirects are refused. Environment proxy inheritance is disabled. The source
host/path, response media type, CRS and API version are validated.

Explicit record, page, per-response byte and total-byte budgets prevent
unbounded source behaviour.

## Reviewed real-source verification

A complete source retrieval was performed on 21 September 2026.

Retrieval ran from:

`2026-09-21T00:13:05.244589+00:00`

to:

`2026-09-21T00:15:22.334466+00:00`

for 137.089877 seconds.

The bundle contained:

- 66,300 sampling points;
- 66,300 located sampling points;
- 0 unlocated sampling points;
- 266 pages;
- 82,405,025 raw response bytes.

The first 265 pages contained 250 records and the final page contained 50.
Every reviewed page reported the same 66,300-record total.

All 66,300 records had the same reviewed source-field shape. No reviewed
preferred label, status, point type, region, area or sub-area was null.

Observed coordinate bounds were longitude -6.354 to 1.7965 and latitude
49.8896 to 56.02.

Content SHA-256:

`2c5da92d010430a078e4c7aa40318aeb46de4e56a1a15e69fb84859917bc11c1`

Normalized SHA-256:

`21433969c0803233499c76e336af0e03a9335de6fdd28f44b9ebbaaa1b8c2d9f`

The first normalization attempt correctly failed because WaterGeo's initial
identifier character assumption excluded publisher notations containing `/`.
A local review of all 66,300 already-retrieved records also found publisher
notations containing spaces.

The identifier contract was narrowed to the actual reviewed publisher behaviour,
regression tests were added, and the same immutable completed evidence bundle
was then re-read successfully. No second publisher retrieval was required.

## Consequences

WaterGeo now has a tested, bounded sampling-point evidence layer for the current
Environment Agency Water Quality Explorer.

The implementation preserves unusual publisher identifiers rather than silently
rewriting them.

Explicit WGS84 negotiation avoids an undocumented conversion from the source's
default BNG representation.

The evidence bundle is substantially larger than the Hydrology snapshot because
the service caps this representation at 250 records per page. Complete retrieval
therefore requires hundreds of publisher requests and intentionally takes
longer because requests are paced.

Database modelling can now be based on the complete reviewed source population
instead of a small sample.

## Out of scope

This ADR does not:

- create water-quality database tables;
- expose a public WaterGeo water-quality API;
- ingest samples or samplings;
- ingest observations;
- ingest determinand or unit codelists;
- infer water-company ownership from sampling-point labels or types;
- infer catchment relationships;
- infer Hydrology relationships;
- schedule refreshes; or
- define freshness thresholds.

Those decisions require separate reviewed source contracts.
