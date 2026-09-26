# Phase 9 company-source selection

Reviewed 2026-09-26. Phase 9 selects one source: Thames Water's public discharge-
status API v2.0.1. One source meets the complete WaterGeo bar; adding a second would
weaken the licence or provenance contract.

| Candidate | Decision | Evidence |
| --- | --- | --- |
| Thames Water discharge status | Selected | Payload names the publisher, API version, documentation and licence; 573 stable `TWL` IDs; BNG coordinates; current status and dated transitions; unauthenticated bounded retrieval |
| Yorkshire Water EDM | Deferred | Useful monthly and annual XLSX data with grid references and Water Body labels, but the reviewed download page does not attach an explicit reusable licence to those artifacts. Files are republished during validation, requiring edition rules before ingestion. |
| United Utilities EDM | Rejected for this phase | The reviewed page explains 2,264 monitored overflows and annual reporting, but exposes no artifact-level open licence in the page contract. Annual EDM also substantially overlaps the national EA return. |
| Northumbrian Water open data | Deferred | The hub applies CC BY 4.0 to named APR datasets, but the reviewed catalog did not provide a stronger operational, dated, geospatial source than Thames status. |

Thames Water's API response links its [Open Data Terms](https://data.thameswater.co.uk/s/terms-of-service)
and [API documentation](https://docs.api.thameswater.co.uk/). Thames Water's official
[open-data rationale](https://www.thameswater.co.uk/media-library/wgjpv14x/our-open-data-rationale-2024-25.pdf)
describes the terms as a worldwide, royalty-free, perpetual, non-exclusive licence
with attribution. The [publisher's discharge page](https://www.thameswater.co.uk/about-us/performance/river-health/storm-discharge-and-flow-data)
documents the API and warns that EDM monitor indications can be inaccurate.

Yorkshire publishes valuable [monthly/annual EDM material](https://www.yorkshirewater.com/environment/river-health/storm-overflow-investment/event-duration-monitoring/),
but its [open-data page](https://www.yorkshirewater.com/about-us/what-we-do/open-data/)
distinguishes freely available files from explicitly licensed open data and describes
licensing infrastructure as work in progress. United Utilities' [storm-overflow page](https://www.unitedutilities.com/better-rivers/our-challenges/storm-overflow-performance/)
documents sensor and annual-return semantics without an explicit licence for the
downloaded records. These sources can be reconsidered when a particular artifact has
durable identity, machine-readable access and an attached licence.

Selection does not assert any relationship between Thames sites, EA Water Bodies,
sampling points, hydrology stations or Ofwat boundaries.
