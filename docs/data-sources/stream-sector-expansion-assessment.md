# Stream and water-company expansion assessment

**Decision: assess and defer a new national Stream ingestion contract.**

Official Water UK material describes a National Storm Overflows Hub covering all
English company overflows and an API. Ofwat describes Stream as the sector sharing
platform. The public catalogue also contains company and use-case datasets under
open licences. The material reviewed in September 2026 did not provide one stable,
versioned, publisher-owned API specification with completeness markers, common
identifiers, timestamp rules and licence metadata sufficient for WaterGeo ingestion.

| Candidate | Coverage/schema | Mechanism/licence | Update/geography | Stability and decision |
| --- | --- | --- | --- | --- |
| National near-real-time EDM | English wastewater companies; common public map claimed | Hub API is referenced; precise contract and licence response need acceptance | operational, point locations | high value, but defer until official schema/version/completeness and licence are machine-verifiable |
| EA annual EDM returns | ten English WaSCs; regulator-normalised annual workbook | official annual ZIP, OGL | annual, EPSG:27700 | feasible next analytical product; prefer this regulator publication over 10 scrapers |
| Reservoir levels | company-specific schemas/editions | Stream/ArcGIS/downloads; often CC BY | company geographies, varied cadence | retain reviewed Severn Trent product; define a cross-company schema before expansion |
| Sewer catchments | incomplete company coverage and different geometry models | mixed portals/downloads | versioned polygons | not yet a national contract |
| Company water-quality monitoring | different determinands, sampling and licences | mixed | point/series | require use-case-specific harmonisation; do not imply comparability |
| Supply interruption / sewer flooding | predominantly regulatory aggregates or company APR tables | Ofwat/company publications | annual/company geography | ingest through generic Ofwat performance measures where defined |

The recommended next contract is the Environment Agency annual national EDM return:
one regulator, OGL, ten-company coverage, annual versioning, published guidance and a
bounded analytical shape. Near-real-time hub integration should follow only after its
official API contract can be pinned and tested. Phase 15 does not build bespoke company
scrapers or weaken evidence standards.

