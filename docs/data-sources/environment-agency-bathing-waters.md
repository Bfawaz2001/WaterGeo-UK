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

## Daily pollution-risk forecasts are a separate candidate

The Environment Agency's
[bathing-water quality service](https://environment.data.gov.uk/bwq/profiles/)
and [Swimfo guidance](https://environment.data.gov.uk/bwq/profiles/help-understanding-data.html)
distinguish annual compliance classification from short-term pollution-risk forecasts.
Forecasts are seasonal, site-specific and not available for every designated bathing
water; their validity window, advice state and absence/out-of-season meanings require
a separate contract. Weather, tides and other predictive inputs do not turn an annual
classification into a daily safety result.

Phase 18B may assess the official forecast endpoint, licensing, eligible-site coverage,
issue/expiry times and failure states. No unattended forecast ingestion or live safety
claim is implemented in Phase 18A.1. The current `latestRiskPrediction` field remains
publisher context only and must not be presented as a WaterGeo safe-to-swim judgement.

## Local acceptance on 29 September 2026

The bounded official response produced 464 bathing-water locations. It included 451
published compliance classifications, 464 latest-sample relations and 453 current risk
prediction values. No record was rejected or skipped; 13 locations correctly retain a
null classification and assessment year.
