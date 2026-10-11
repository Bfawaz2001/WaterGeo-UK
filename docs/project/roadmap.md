# Roadmap

## Delivered

- Governed ingestion and snapshot-based PostGIS/API products for ten source families.
- Static GitHub Pages explorer with accepted evidence and publication provenance.
- Snapshot-aware SDK/CLI, bounded history and selected-feature detail.
- Optional GeoJSON, PMTiles, Parquet/GeoParquet exports and Fabric consumption guidance.
- Six dynamic refresh workflows and a sequential local refresh command.

These are implemented capabilities, not guarantees that external schedules, cloud
resources or a hosted public API are running. See [history](development-history.md).

## Phase 17B — delivered

Documentation architecture, regional orientation, explicit filter-to-map navigation,
flood severity filtering, accessible controls and supported OpenFreeMap fonts.
Regional rectangles and nearby clusters are not national feature distributions.
No new source, national tile-generation service or deployment automation is included.

## Phase 18A — current review scope

Explorer intelligence and data clarity using existing accepted contracts: readable
rainfall and Hydrology measures, exact bathing-water classification filters over
bounded loaded results, explicit Water Quality capability states, Rivers & Catchments
hierarchy, company/area search grouping, regional discovery guidance and clearer
observation/retrieval/publication timing. No publisher, ingestion, database or static
publication schema is added by this work.

## Future, separately reviewed work

| Workstream | Remaining decision / deliverable |
| --- | --- |
| Phase 18B history and analytics | Governed rainfall history; UI for existing bounded Hydrology and Water Quality observation evidence; measure-safe charts without joining incompatible units/statistics |
| Phase 18C national distribution | Lightweight accepted point overview/tiles, completeness metadata and zoom handoff; avoid treating nearest-100 clusters as nationwide coverage |
| Public API readiness | Hosting, authentication/access policy, rate limits, monitoring and operating budget; current public hosting is static only |
| Static publication automation | Govern refresh → retained evidence → build → protected deploy, with failure alerts and rollback review |
| Fabric interoperability | Validate tenant-specific Lakehouse/Map/Power BI integrations against export contracts; keep vendor SDKs optional |
| Operational observability | Deployment-specific alerts, freshness policy dashboards, durable evidence retention and tested recovery at current schema |
| Source opportunities | Reassess documented Stream/company candidates only with stable schema, licensing and provenance contracts |

The optional water-supply overview already exists; national point tiling and dynamic
source tiles are separate work. Water Body tiling, unit conversion and cross-source
spatial assignments are not implied by current exports. The legacy backup rehearsal's
`0011` guard also needs a separately scoped update before it can accept the current
`0012` runtime; do not treat it as current recovery evidence.

Prioritization is subject to review. No future item here is a deployment commitment,
publisher SLA or promise of live observations.
