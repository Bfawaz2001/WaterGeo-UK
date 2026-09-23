# Water Quality observation contract review

Reviewed 2026-09-22 against the live public [OpenAPI](https://environment.data.gov.uk/water-quality/api/swagger),
Water Quality Archive 1.3.1, OpenAPI 3.1.0, API-Version 1.
The 63,435-byte OpenAPI SHA-256 was
`013f828198b2b1fe6068aa58602c2706dacfc11ffd3b2c0393bcc4925db0d4d6`.

## Small public probes before implementation

`POST /water-quality/data/observation` with JSON `null`, JSON-LD Accept,
API-Version 1 and EPSG:4326 Accept-Crs, query
`pointNotation=AN-CORBY&dateFrom=2020-01-01&dateTo=2020-01-31&limit=2&skip=0`
returned HTTP 200, two members and totalItems 14. The 5,665 response bytes hashed to
`6815a223f23ae577e9d996db80b5126d496c247d9d7e4e70d4149af950534dd2`.
No full-archive retrieval is intended.

The collection context is `wqa_observation_context.json-ld`; Hydra pagination links
use HTTP and are not followed. Fixed HTTPS URLs must be constructed with bounded
`skip`/`limit` and unchanged scope. OpenAPI exposes no observation sort parameter or
snapshot token. Stable total and duplicate checks detect some concurrent changes,
but cannot prove a publisher-atomic traversal.

Observed relationships:

- Observation `/sampling-point/AN-CORBY/sample/1959118/observation/0085`.
- `hasSample.id` ends `/sample/1959118`; `hasSample.isResultOf.id` ends `/sampling/1959118`.
- `phenomenonTime` is `2020-01-23T11:51:00`, **without a timezone**. Do not assert UTC.
- `hasSimpleResult` is `<0.98`; quantity numericValue is null, upperBound is 0.98,
  lowerBound is null. Censored results must not become a measured value of 0.98.
- Determinand notation `0085`, BOD : 5 Day ATU; unit notation `205`, MILLIGRAM PER LITRE,
  symbol `mg/l`. Embedded `@id` values are blank-node identifiers, not globally unique URIs.
- The other probed observation has determinand `0076`, temperature 14.7, unit `349`/CEL.
- Source sampling-purpose and sample-material concepts are embedded in the sample chain.

Single-entry `GET /codelist/determinand?notation=0085&limit=250&skip=0` and
`GET /codelist/unit?notation=205&limit=250&skip=0` each returned one matching member,
context `wqa_codelist_context.json-ld`, `view: null`, and matching labels/notations.
The codelists expose notation, prefLabel, altLabel and source blank-node identity.

## Accepted implementation scope

One explicit sampling-point notation and determinand, start-inclusive/end-exclusive
date-only bounds spanning 1–31 calendar days. A follow-up same-day `2020-01-23`/`2020-01-23`
probe returned zero rows; `2020-01-23`/`2020-01-24` returned the 11:51 observation.
Thus dateTo must not be presented as an inclusive whole day. WaterGeo rejects returned
timestamps outside its half-open window, including any exact upper-bound midnight row;
the publisher's precise equality behavior at midnight was not established by these probes.
No full archive, arbitrary upstream URL, inferred identities,
unit conversions or UTC assignment. Preserve original timestamp text, result text,
numeric value and lower/upper bounds separately, along with exact observation, sample
and sampling IDs. Retrieve the scoped determinand and referenced units as immutable
evidence with each retrieval. Keep publisher sample/purpose/material metadata.

Apply page/record/byte limits, consistent reported totals, duplicate rejection and
scope validation to all returned observations. Later corrected retrievals coexist;
exact evidence retries must verify stored metadata and children. Empty scoped
retrievals are valid evidence, not a claim that the sampling point has no history.

Licensing and independence follow the [sampling-point source assessment](environment-agency-water-quality.md).

## Retained end-to-end verification

On 2026-09-22, the accepted AN-CORBY / 0085 scope `[2020-01-23, 2020-01-24)`
produced one observation, one determinand response and one unit response: three
responses totaling 3,252 bytes. Retained bundle:
`data/raw/refresh/water-quality-observations/79ae1843-520b-41b5-adb9-b7d964f863ea/0a81a9a7-f122-470e-896e-d6ad90feca8c`.

- Content SHA-256: `affaf9eff0271e2650b46dd6fcd36fdd585a446ea5e846e3579a3bdaedad2607`.
- Normalized SHA-256: `e0a39b8bfb55b11c111d5c87872b9964c0ea2e8edd8afa34e77817184636a3bb`.
- Normalization version: `ea-water-quality-observations-v1`.

The disposable database first required the retained 66,300-point metadata snapshot.
Offline publication then inserted the observation; retry returned verified `existing`.
The application-role HTTP endpoint returned 200, one row, `<0.98`, upper bound 0.98
and null numeric value. Test database UUIDs are ephemeral, not portable evidence IDs.
The diagnostic zero-length date probe is retained locally but is outside the accepted
1–31-day contract and cannot be published by the final implementation.

## Operational and semantic limits

At most 250 observations per page, 20 observation pages, 5,000 observations,
20 referenced units, 16 MiB per response and 64 MiB combined response bytes.
Requests have bounded retries and timeouts; the refresh supervisor imposes a total
deadline. Offline reads recheck request scope, response headers, sizes, hashes and
normalized content. Missing values remain null; contradictory result/bound text or
unreviewed timestamp and relationship shapes fail closed. No value interpolation,
unit conversion or water-safety judgment is derived.

The source can change during pagination, and consistent totals cannot prove that no
replacement occurred. Evidence therefore describes the bounded retrieval, not a
publisher-atomic archive edition. New evidence can coexist as a later correction;
exact retries verify stored observation and codelist content before returning a no-op.
Retrieval timestamps are timezone-aware operational facts; original phenomenonTime
has no assumed timezone. Sample material and sampling purpose remain publisher
metadata in the preserved Sample/Sampling chain rather than inferred classifications.

See [ADR 0012](../adr/0012-bounded-water-quality-observations.md) and the
[developer walkthrough](../guides/water-quality-walkthrough.md).
