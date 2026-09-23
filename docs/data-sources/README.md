# Data source acceptance

The reviewed Ofwat water-supply source is integrated; its source assessment and
ADRs define the accepted scope. Environment Agency river level/flow hydrology
is also integrated under its separate source assessment and ADR 0007. Public
availability alone is not permission to redistribute.
For each proposed integration, record the following from current
official documentation and actual sample responses before implementation:

1. Publisher, dataset title, official source URL, and documentation/API links.
2. Licence name/version/link, permitted persistence/caching/redistribution, exact
   required attribution, and any source-specific terms or unresolved questions.
3. Date reviewed, retrieval method, documented update frequency, observed source
   update/version fields, rate limits, and availability limitations.
4. Source schema and identifiers, geography/coverage, coordinate reference system,
   geometry types, temporal semantics, nulls, and known data-quality constraints.
5. Proposed transformations and retained source-specific fields, deduplication
   keys, raw retention, incremental/replacement policy, and deletion handling.
6. How each resulting record links to its publisher, dataset, original identifier,
   source URL, licence, ingestion timestamp, source version/update information,
   and transformation version where appropriate.

Record evidence and uncertainties explicitly. Stop implementation if licence
conditions remain unclear. Use only public sources; employment access confers no
rights on this project. Do not put bulk source data in Git. Keep small fixtures
synthetic or verify and record their redistribution rights.

## Assessments

- [Stream and water-company public sources](stream-company-source-assessment.md),
  reviewed 23 September 2026: 426 public Stream catalogue items compared using explicit
  licence/access/identity/quality criteria. Severn Trent Water's CC BY 4.0 2025
  reservoir-level edition was selected; 14 reservoirs and 728 readings were verified.

- [Environment Agency Water Quality sampling points](environment-agency-water-quality.md)
  and [bounded observations](environment-agency-water-quality-observations.md), reviewed
  22 September 2026: 66,300 retained sampling points; a one-day AN-CORBY/0085
  observation retrieval verified through publication, retry and HTTP. ADRs 0011/0012
  define the accepted metadata and observation contracts and limitations.

- [Ofwat water-company boundaries](ofwat-company-boundaries.md), reviewed
  17 September 2026: publisher OGL declaration confirmed; exact edition remains
  unverified. Empty schema and synthetic geometry tests implemented, with real-data
  integration pending the edition/final attribution check and resolution of invalid
  geometries. Includes measured schema,
  quality findings, and comparisons with OpenPostcodes and MOSL; no integration
  implemented. Missing bespoke attribution alone does not require publisher contact.

- [Environment Agency Catchment Data Explorer Cycle 3](environment-agency-catchment-data-explorer-verification.json),
  reviewed 20 September 2026: authoritative Cycle 3 hierarchy verified as
  10 River Basin Districts, 117 Management Catchments, 750 Operational Catchments
  and 4,929 Water Bodies, with 8,701 publisher Water Body geometry features.
  Phase 2C does not assert or infer a Hydrology station-to-catchment relationship.
