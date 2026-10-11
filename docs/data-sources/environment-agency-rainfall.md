# Environment Agency rainfall

## Accepted publisher contract

- **Publisher:** Environment Agency.
- **Official service:** [Rainfall API documentation](https://environment.data.gov.uk/flood-monitoring/doc/rainfall) and the Flood Monitoring API `id/stations` / `data/readings` endpoints.
- **Licence:** Open Government Licence 3.0, using the licence URI returned by API version 0.9.
- **Identity:** station `notation`, which the publisher documents as the unique item notation;
  `stationReference` is retained in raw evidence but is not unique in the live national response.
  Measure URI is the reading identity.
- **Measurement:** the publisher describes its rainfall series as 15-minute accumulated
  rainfall, while each measure also declares its own unit and period. WaterGeo retains that
  declared period rather than assuming 15 minutes. The accepted live response contained
  `mm` measures at 900 and 3,600 seconds. `dateTime` is the observation time; WaterGeo
  retrieval time remains separate.
- **Geography:** publisher WGS84 latitude/longitude. The publisher says names may be absent and positions are reduced to a 100 m grid. WaterGeo retains that precision and does not infer names or locations.

The API describes roughly 1,000 telemetry gauges and states that data transfer is typically once or twice daily, but can increase during high rainfall. Publisher transfer cadence, measure period, observation time, WaterGeo retrieval time and static publication time are separate; none alone is a freshness guarantee.

## WaterGeo contract

Each bounded retrieval retains exact station and latest-reading responses before strict validation. WaterGeo rejects licence, API-version, identifier, measure-period, unit, timestamp, coordinate or completeness drift. An accepted append-only snapshot powers the API, map, static snapshot and optional GeoParquet export. No unlimited rainfall history is retained.

The explorer uses the accepted publisher label when present and otherwise displays
`Rainfall gauge <publisher ID>`. It never derives a name from nearby features or an
external search. Detail shows the exact gauge ID, declared unit and period, publisher
observation time and separate WaterGeo retrieval time. A missing latest observation is
labelled unavailable and remains distinct from numeric zero. Historical rainfall series
and charts require a separately governed history product and are deferred to Phase 18B.

Official GOV.UK station pages can carry a human-readable name for an exact gauge
identity: for example, station `075497` is published as
[Bradford Chellow Heights gauge](https://check-for-flooding.service.gov.uk/rainfall-station/075497).
That page is useful verification evidence but is not part of the accepted national
feed contract. Adding names therefore needs a separately retained official-identity
crosswalk with licence, retrieval, conflict and missing-name rules. Until that review,
the canonical identifier fallback remains deliberate; WaterGeo does not scrape search
results or reverse-geocode the feed's reduced-precision coordinates.

The reviewed live response contains one empty root station record and can contain a latest
reading whose measure is absent from the station response. WaterGeo retains both in raw
evidence, excludes them from canonical station/latest associations, and records the exact
skipped count. Any other malformed identity still fails closed.

Hosted refresh is hourly at `:27` UTC and remains opt-in through `WATERGEO_RAINFALL_SCHEDULE_ENABLED`. Static publication is a separate daily snapshot policy.

## Local acceptance on 29 September 2026

The bounded official response produced 1,044 stations, 934 latest measure readings and
928 stations with an associated latest observation. Of those stations, 1,041 had
publisher coordinates. Two publisher artifacts were retained in raw evidence and
recorded as skipped: the empty root station record and one reading without a returned
station association.

## Rejected refresh on 11 October 2026

Run `8de834a2-bef3-49e0-8f97-9a2bc3956842` retained exact bounded station and reading
responses before normalization. The response was successful JSON, within the 2 MiB
bound, but one of 932 reading items supplied `value: [0.0, 0.0]` for measure
`008850-rainfall-tipping_bucket_raingauge-t-15_min-mm` at
`2026-10-08T08:00:00Z`. The reviewed contract permits a scalar number or null, not a
list. The same anomaly is present in the other retained rejected attempts inspected
from 10–11 October.

WaterGeo therefore rejected the bundle with `Invalid rainfall value`, archived its
evidence and left the 30 September accepted snapshot available. It did not load a
partial snapshot or reinterpret the list as a scalar. There is no authoritative rule
for choosing or combining those two values, so validation has not been relaxed. This
is a safe source-contract rejection, not evidence that the entire publisher service
was unavailable. A future compatible publisher correction can pass the unchanged
contract; repeated live requests are not required for diagnosis.
