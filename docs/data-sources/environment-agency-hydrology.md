# Environment Agency hydrology source assessment

Reviewed: 2026-09-19. Status: implemented and verified for the river level/flow
scope, including explicitly absent station locations. Phase 1 remains complete.

## Official sources and selected scope

Publisher: Environment Agency (EA). Both APIs are public and require no credentials.

| Source | Official documentation and root | Assessment |
| --- | --- | --- |
| Hydrology | [Reference](https://environment.data.gov.uk/hydrology/doc/reference), `https://environment.data.gov.uk/hydrology` | Preferred for this slice: station/measure identities, qualified series, reading-quality flags and future history. Observed API version 2.1.1. |
| Flood Monitoring | [Reference](https://environment.data.gov.uk/flood-monitoring/doc/reference), `https://environment.data.gov.uk/flood-monitoring` | Useful for near-real-time telemetry. Observed API version 0.9; response ambiguities need a separate acceptance policy. |

Implemented scope is Hydrology `observedProperty=waterLevel` OR `waterFlow`.
Rainfall, groundwater, water quality and flood alerts are outside this first slice.
The [official dataset catalogue](https://environment.data.gov.uk/dataset/4da28d02-8997-4b0f-9d83-3c5d958a1c65)
describes England coverage, not a complete UK network. Actual geographic bounds
are recorded in the evidence file; they do not establish national completeness.

## Licence and attribution

Both sampled APIs explicitly link Open Government Licence version 3 in their
response metadata. Hydrology additionally returns `licenseName: OGL 3`.
Preserve [OGL v3](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
and publisher attribution separately from WaterGeo's MIT code licence.
The official Hydrological Open Data catalogue supplies this attribution:

> © Environment Agency copyright and/or database right 2015. All rights reserved.

Flood Monitoring has its own attribution wording in its reference; it must be
retained if that source is integrated later. This assessment does not substitute
one API's attribution or identity contract for the other's.

## Identity, location and measurement semantics

- Station `notation` and `@id` are publisher identifiers. Preserve both exactly.
  `stationGuid` alone is insufficient: composite notations distinguish sampling
  locations. `wiskiID` is an additional identifier, not a replacement primary key.
- Measures have their own `notation` and URI and link to a station URI. Preserve
  parameter, parameter name, observed property, observation type, unit URI/name,
  period, period name and value statistic. Similar labels do not imply equality.
- Readings link to a measure URI; the pair of measure identity and `dateTime`
  identifies an observation. Latest responses need at most one reading per measure;
  conflicting duplicates must reject retrieval rather than select arbitrarily.
- Station `lat`/`long` support WGS84 Point storage. British National Grid easting
  and northing also occur. Preserve original fields, without inventing coordinates.
  Banks Road lacks both representations (see the accepted policy below).
- Labels and status can be multi-valued. Preserve the source values. River names
  are optional: 224 scoped stations lack them. All 2,982 sampled station records
  lack `catchmentName`; do not manufacture a catchment relationship.
- An active status does not guarantee a recent observation. Observation quality
  and completeness belong to each reading, separately from station status.

## Time, freshness, missing values and corrections

The [official GMT FAQ](https://environment.data.gov.uk/support/faqs/275875350/275875667)
states that hydrological data uses GMT, including during British Summer Time.
Actual Hydrology responses contain timestamps without an offset. A source-specific
adapter may explicitly attach UTC under that documented contract, preserve the raw
string and expose an aware UTC timestamp. Generic naive-time guessing is unsafe.

The catalogue describes daily and monthly publication of different products;
measurement period is not publication cadence. Flood Monitoring describes typical
15-minute sampling, with transmission varying by station. Neither is an assurance
that every latest observation is current. The scoped sample's latest timestamps
range from 2003-02-17 to 2026-09-19. Expose retrieval time and observation time
separately, using “latest available observation”. Source Last-Modified, if returned,
is response metadata, not automatically an observation update timestamp.

There are 83 measures without a latest observation and 67 returned observations
with quality `Missing` and no numeric value. Keep these states distinct from the
155 numeric zero readings. Preserve quality, completeness and source fields such
as valid/invalid/missing proportions without undocumented numeric reinterpretation.
Non-finite values, booleans masquerading as numbers and malformed times must fail.
Records may be corrected after publication. Retrieval snapshots are observations
of a changing API, not immutable publisher editions. Bounded historical retrieval
is now implemented as a separate evidence product. A later retrieval of the same
measure/time window may legitimately contain different publisher content and is
therefore stored separately rather than updating an earlier retrieval.

## Requests, limits and completeness

The research request URLs, effective limits, counts and exact response hashes are
in [the evidence summary](environment-agency-hydrology-assessment.json).
Use station/measure endpoints under `/id` and readings under `/data/readings`.
Repeat `observedProperty` to express the two-property scope. The readings endpoint
supports `latest`. A trial using `measure.observedProperty` instead returned zero
items: it is not the documented readings filter and is excluded from the evidence.

Hydrology supports `_limit`/`_offset` and sorting. Readings have a documented default
100,000-row limit and a currently documented hard maximum of 2,000,000, subject to
change. Inspect effective metadata limits instead of assuming requested limits.

For historical observations, the reviewed endpoint is
`/hydrology/id/measures/{measure_id}/readings`. Empirical source verification on
2026-09-19 confirmed inclusive `mineq-dateTime` / `maxeq-dateTime` filters,
timezone-aware `Z` request values, `_sort=dateTime`, `_limit` and `_offset`.
The first page may omit `meta.offset`; subsequent pages report it. WaterGeo limits
one historical retrieval to one measure and at most 31 days, validates every page
and duplicate timestamp, and records each request URL and response hash.

A reviewed 31-day level-series sample returned 3,041 unique measure/timestamp pairs
with no duplicate timestamps. This is evidence for the bounded retrieval design,
not a claim that publisher measure/timestamp pairs are globally immutable.
The publisher asks clients to keep one request in flight; no fixed requests-per-
minute allowance was found. Requests may be blocked for excessive use.

A production client must enforce explicit request, byte, page and record budgets;
validate page identities, duplicates, terminal pagination and cross-references;
and reject partial snapshots. Stable station/measure sorting helps, but no documented
cross-endpoint transaction token was found. Retrieval-window provenance must expose
that limitation. Research used one response per scoped entity, below its declared
limit; this is not production pagination or atomic-ingestion verification.

## Actual source problems and accepted missing-location contract

Hydrology returned 2,982 stations, 12,326 measures and 12,243 latest observations.
No duplicate station/measure identities, duplicate latest-measure identities or
broken station/measure references were found in those responses.

**Banks Road**, notation `32f5b1ea-29f7-4d6c-b473-a9e5da0e59d1_U30028`, has no
latitude, longitude, easting or northing. This was independently confirmed in its
[individual station response](https://environment.data.gov.uk/hydrology/id/stations/32f5b1ea-29f7-4d6c-b473-a9e5da0e59d1_U30028).
It is marked active and has four flow measures. Do not substitute a similarly
named station, infer coordinates from its GUID or silently discard it.

Accepted contract: retain unlocated stations, their measures and observations;
return null geometry and `location_status: unavailable`; include them in list/detail;
and disclose total/located/unlocated counts in dataset and nearby-search metadata.
Nearby search cannot determine their distance and excludes them explicitly.
Malformed, partial or non-finite supplied coordinates reject the entire snapshot.
A BNG-only location requires assessment rather than an inferred WGS84 replacement.
No station ID or permanent missing-location count is hard-coded.

WGS84 coordinates are the canonical source representation. Supplied BNG fields
must be a complete finite numeric pair, but are retained without conversion or a
cross-CRS equality claim. This contract does not define a datum/rounding agreement
tolerance; cross-CRS positional accuracy is not established by ingestion validation.
If a source conflict is found during review, reassess rather than substituting a
coordinate. A drop of more than one percentage point in located-station fraction
against the latest loaded compatible snapshot rejects publication for review. First
loads require checking the verification summary against the reviewed source scope.

Flood Monitoring is not a clean substitute: its research responses contain 632
stations without coordinates, one station with conflicting coordinate arrays,
orphan station references in measures, and one latest reading with two different
numeric values. Selecting a value or dropping records would violate the contract.

## Evidence retention and limitations

Raw scoped responses and a research manifest are retained locally beneath ignored
`data/raw/environment-agency/hydrology/2026-09-19-assessment/`. Only the small
summary is intended for Git. Research did not retain request start/end times or
response headers; local file timestamps are labelled accordingly. That research
summary alone does not establish production retrieval or ingestion
verification; the completed run below supplies the missing evidence.

The completed timed retrieval and database/HTTP verification are recorded separately
in [verification evidence](environment-agency-hydrology-verification.json). It records
three response pages retrieved in 83.028 seconds, the same counts as research, no
duplicates or validation failures, all 2,982 station detail HTTP responses, and a
verified no-op on exact-content retry. Responses supplied Date and Content-Type;
ETag and Last-Modified were absent, so neither is invented.

A real bounded history verification on 2026-09-19 retrieved 81 observations for
measure `c7e13884-4a02-4df3-b184-09aea28cf8e8-level-i-900-m-qualified` over
`2026-09-19T00:00:00Z` to `2026-09-19T20:15:00Z`. The evidence loaded atomically;
an exact retry returned the same stored retrieval after child-row verification,
and the public retrieval endpoint returned the stored observations with cursor
pagination and `Cache-Control: no-store`.

See [ADR 0007](../adr/0007-environment-agency-hydrology.md) for snapshot ingestion
and [ADR 0008](../adr/0008-hydrology-history.md) for bounded historical evidence.
