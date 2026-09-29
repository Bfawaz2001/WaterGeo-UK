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
