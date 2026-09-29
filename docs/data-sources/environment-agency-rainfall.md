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
