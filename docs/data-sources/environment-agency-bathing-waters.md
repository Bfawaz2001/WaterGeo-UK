# Environment Agency bathing waters

## Accepted publisher contract

- **Publisher:** Environment Agency / Defra linked-data service.
- **Official machine endpoint:** `https://environment.data.gov.uk/doc/bathing-water.json`.
- **Licence:** Open Government Licence 3.0.
- **Identity:** `eubwidNotation`; the publisher URI is retained separately.
- **Geography:** sampling-point latitude/longitude in WGS84.
- **Classification:** exact latest compliance-classification term and the assessment year encoded by the official assessment URI.
- **Sample/advice context:** WaterGeo retains the official `latestSampleAssessment` relation and `latestRiskPrediction` value when present. It does not turn either into a health judgement.

The linked-data response must declare format `linked-data-api`, version `0.2`, contain one bounded page and provide stable identities and coordinates. Some current designated records do not yet carry a compliance assessment; WaterGeo preserves classification and assessment year as null for those records instead of inventing a value. Evidence bytes are written before parsing and validation. Classification year, sample relation, publisher risk/advice context and WaterGeo retrieval time remain distinct.

Bathing-water monitoring is seasonal. WaterGeo retrieves weekly during May–September and monthly outside that period, behind `WATERGEO_BATHING_WATERS_SCHEDULE_ENABLED`. This cadence is not a claim that classifications or samples change on that schedule. WaterGeo does not state whether a location is safe to swim.

The explorer filters the exact publisher terms `Excellent`, `Good`, `Sufficient` and
`Poor`, plus null as `Unclassified / no published classification`. The filter applies
to the bounded nearest results already loaded around the map, so its count is explicitly
local and is not a national total. Classification colour is supplemented by text. A
one-shot action can fit matching loaded points without creating a refit loop. The detail
panel shows assessment year and keeps annual classification separate from samples,
short-term advice and daily swimming-safety decisions.

## Local acceptance on 29 September 2026

The bounded official response produced 464 bathing-water locations. It included 451
published compliance classifications, 464 latest-sample relations and 453 current risk
prediction values. No record was rejected or skipped; 13 locations correctly retain a
null classification and assessment year.
