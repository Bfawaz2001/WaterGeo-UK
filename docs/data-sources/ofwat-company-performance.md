# Ofwat company performance

## Accepted publications

- [Water Company Performance Report 2024–25 machine-readable data](https://www.ofwat.gov.uk/publication/data-for-the-water-company-performance-report-2024-25-open-data-friendly-machine-readable-format/).
- [PR24 historical performance trends V6.0](https://www.ofwat.gov.uk/publication/historical-performance-trends-for-pr24-v6-0/), published 15 January 2026 and covering data through 2024–25.
- **Publisher/licence:** Ofwat, Open Government Licence 3.0.

The WaterGeo preparation contract records the exact publication, publisher company identifier/name, reporting period, measure code/name, numeric value or explicit `missing` / `not_applicable` state, unit and definition/source metadata. Zero remains a reported numeric value. Regulatory facts are not recast as WaterGeo ratings.

## Boundary crosswalk

Company performance has no point geometry. It may attach to a selected water-supply area only through the reviewed `ofwat-to-water-supply-v1` crosswalk included in accepted evidence. The normalizer rejects row-level mapping fields and unknown crosswalk versions. Mapping is by exact publisher/company identity to the exact boundary acronym; no fuzzy company-name join occurs. Unmapped companies remain unmapped.

Ofwat editions are publication-driven. There is no polling workflow. An operator prepares and reviews one bounded JSON evidence bundle from the official machine-readable edition, including its checksum and crosswalk, before loading it. Static JSON and optional Parquet preserve the edition, period, measure definitions and provenance.

