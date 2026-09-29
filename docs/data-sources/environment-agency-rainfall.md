# Environment Agency rainfall

## Accepted publisher contract

- **Publisher:** Environment Agency.
- **Official service:** [Rainfall API documentation](https://environment.data.gov.uk/flood-monitoring/doc/rainfall) and the Flood Monitoring API `id/stations` / `data/readings` endpoints.
- **Licence:** Open Government Licence 3.0, using the licence URI returned by API version 0.9.
- **Identity:** station `notation`, which the publisher documents as the unique item notation;
  `stationReference` is retained in raw evidence but is not unique in the live national response.
  Measure URI is the reading identity.
- **Measurement:** accumulated rainfall in `mm` over a publisher-declared 900-second period. `dateTime` is the observation time; WaterGeo retrieval time remains separate.
- **Geography:** publisher WGS84 latitude/longitude. The publisher says names may be absent and positions are reduced to a 100 m grid. WaterGeo retains that precision and does not infer names or locations.

The API describes roughly 1,000 telemetry gauges and states that data transfer is typically once or twice daily, but can increase during high rainfall. Neither the 15-minute measurement period nor WaterGeo's hourly retrieval is a freshness guarantee.

## WaterGeo contract

Each bounded retrieval retains exact station and latest-reading responses before strict validation. WaterGeo rejects licence, API-version, identifier, measure-period, unit, timestamp, coordinate or completeness drift. An accepted append-only snapshot powers the API, map, static snapshot and optional GeoParquet export. No unlimited rainfall history is retained.

The reviewed live response contains one empty root station record and can contain a latest
reading whose measure is absent from the station response. WaterGeo retains both in raw
evidence, excludes them from canonical station/latest associations, and records the exact
skipped count. Any other malformed identity still fails closed.

Hosted refresh is hourly at `:27` UTC and remains opt-in through `WATERGEO_RAINFALL_SCHEDULE_ENABLED`. Static publication is a separate daily snapshot policy.
