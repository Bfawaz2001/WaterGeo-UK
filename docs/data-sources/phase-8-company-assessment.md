# Next company datasets: assessment, 2026-09-26

No additional company source is ingested in Phase 8. Existing reviewed boundaries
already demonstrate national delivery and Fabric consumption. Adding a mutable
operational feed would add licence, refresh and observation semantics to this phase
without being needed for that demonstration.

| Priority | Candidate | Value | Evidence still required before ingestion |
| --- | --- | --- | --- |
| 1 | Yorkshire Water monthly/annual storm-overflow EDM | Dated observations, discharge grid references and permit context; a useful companion to station data without inferring relationships | Exact download-level licence, durable asset IDs across releases, missing-data rules and coordinate review |
| 2 | Thames Water storm-discharge API | Operational event timing and a documented public API | Exact licence/terms, authentication/rate limits, stable asset identifiers, geolocation coverage and semantics for open/closed events |
| 3 | United Utilities storm-overflow performance | Another region and dated sensor-derived annual reporting | Machine-readable edition, exact licence, station identifier stability and coordinates; avoid duplicating EA national annual summaries |

These are recommendations for source reviews, not approved integrations. Public
availability does not establish a reuse licence for every file. Yorkshire's general
open-data policy names open licences, but each selected artifact must still be checked.
Annual EDM duplication should be assessed against a single EA national import before
building separate company pipelines. Event status is not an inference of river safety.

Official evidence:

- [Yorkshire Water EDM, including discharge grid references](https://www.yorkshirewater.com/environment/river-health/storm-overflow-investment/event-duration-monitoring/)
- [Yorkshire Water open-data policy](https://www.yorkshirewater.com/about-us/what-we-do/open-data/)
- [Thames Water storm discharge and flow data](https://www.thameswater.co.uk/about-us/performance/river-health/storm-discharge-and-flow-data)
- [United Utilities storm-overflow performance](https://www.unitedutilities.com/better-rivers/our-challenges/storm-overflow-performance/)
