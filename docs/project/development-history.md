# Development history

This capability history preserves phase references without using them as the
product manual. Consult [current architecture](../architecture/system-overview.md)
for current state; dated ADRs and performance reports describe their review runtime.

| Milestone | Delivered capability | Evidence / guide |
| --- | --- | --- |
| Engineering foundations, Phases 0–1 | Explicit PostGIS migrations and roles; reviewed water-supply ingestion, canonical geometry and separate WGS84 presentation policy | [Foundation](../architecture/phase-0.md), [water-supply walkthrough](../guides/water-supply-walkthrough.md) |
| Source governance, Phase 2 | Hydrology latest and bounded history, CDE hierarchy and publisher Water Body geometry, source status and governed refresh | [Hydrology](../guides/hydrology-walkthrough.md), [source operations](../guides/source-operations.md) |
| Metadata and company editions, Phases 3–4 | Water Quality sampling points and bounded observations; Severn Trent 2025 reservoir locations and dated readings | [Water Quality](../guides/water-quality-walkthrough.md), [reservoirs](../guides/stream-reservoir-levels-walkthrough.md) |
| Consumption and deployment foundations, Phases 5–6 | Snapshot-aware Python SDK/CLI and container/production configuration foundations | [SDK](../guides/developer-quickstart.md), [deployment assessment](../architecture/phase-6-deployment-gap-assessment.md) |
| Explorer and export, Phases 7–8 | React/MapLibre explorer, bounded interactions, optional PMTiles and analytical exports, Fabric compatibility examples | [Explorer](../guides/explorer-local-development.md), [exports](../guides/phase-8-exports.md) |
| Operational and product development, Phases 9–14 | Thames EDM, production rehearsal, unified search, clustering, accessible trends and explorer visual system | [Thames assessment](../data-sources/thames-water-discharge-status.md), [Phase 13 design](../design/phase-13-explorer.md) |
| National data, Phase 15 | Rainfall, flood areas/warnings, bathing waters and reviewed generic company-performance products; immutable static publication | [Portfolio](../data-sources/source-portfolio.md) |
| Public static beta, Phase 16 | Governed ten-source private evidence handoff, deterministic replay, browser acceptance and GitHub Pages launch | [Static publication](../deployment/zero-cost-static-preview.md) |
| Operational maturity, Phase 17A | Current-state documentation, six-product dynamic refresh command, ten-product source status and policy-aware retrieval age | [Refresh and publication](../guides/refresh-and-publication.md) |
| Explorer clarity, Phase 17B | Consolidated architecture docs, regional orientation, explicit filter navigation and publisher flood-state controls | [Navigation design](../design/explorer-navigation.md) |
| Current work, Phase 18A | Readable rainfall/Hydrology details, loaded-scope bathing classification filters, Water Quality capability states, catchment hierarchy and company/area search grouping | [Interpretation guide](../guides/explorer-data-interpretation.md) |

Public hosting refers to static GitHub Pages, not a hosted FastAPI/PostGIS service.
Fabric compatibility does not mean a Fabric deployment was provisioned. New source
opportunities were assessed in earlier phases; assessment alone is not integration.

Water Quality results retain qualifiers and unspecified timezones. Reservoir readings
retain publisher units and the reviewed summer-time offset discrepancy. Historical
retrievals are explicit immutable evidence products; WaterGeo does not silently stitch
overlapping windows into a complete publisher archive. These limitations survive the
product milestones above. See the [roadmap](roadmap.md) for unfinished work.
