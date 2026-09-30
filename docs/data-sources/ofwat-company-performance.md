# Ofwat company performance

## Accepted publications

- [Water Company Performance Report 2024–25 machine-readable data](https://www.ofwat.gov.uk/publication/data-for-the-water-company-performance-report-2024-25-open-data-friendly-machine-readable-format/).
- [PR24 historical performance trends V6.0](https://www.ofwat.gov.uk/publication/historical-performance-trends-for-pr24-v6-0/), published 15 January 2026 and covering data through 2024–25.
- **Publisher/licence:** Ofwat, Open Government Licence 3.0.

The WaterGeo preparation contract records the exact publication, publisher company identifier/name, reporting period, measure code/name, numeric value or explicit `missing` / `not_applicable` state, unit and definition/source metadata. Zero remains a reported numeric value. Regulatory facts are not recast as WaterGeo ratings.

The reviewed 2024–25 contract is
[`ofwat-company-performance-2024-25-review.json`](ofwat-company-performance-2024-25-review.json).
It pins both official source files:

- workbook SHA-256: `62fe9156388f76c04e36cd494ba927124dc7f239928dc0f7e1e257b91168976b`
- data-dictionary SHA-256: `fb0846b78d066a98794b40bb408610e87b996edd3a0542859536ae0eb8412c50`

## Boundary crosswalk

Company performance has no point geometry. It may attach to a selected water-supply area only through the reviewed `ofwat-to-water-supply-v1` crosswalk included in accepted evidence. The normalizer rejects row-level mapping fields and unknown crosswalk versions. Mapping is by exact publisher/company identity to the exact boundary acronym; no fuzzy company-name join occurs. The reviewed edition maps 16 identities. Bristol Water and the CAM, ESK, NNE and SST regional identities remain unmapped because the v1.5 boundary product has no exact corresponding company identity.

Ofwat editions are publication-driven. There is no polling workflow. The bounded
`watergeo-prepare-company-performance` command converts an operator-supplied official
XLSX file into a validated Phase 15 evidence bundle. It requires a reviewed JSON
contract that pins the workbook and data dictionary, names the exact worksheet, maps
every required field to an exact header, declares the missing and not-applicable
vocabularies and reviewed exclusions, and contains the exact
`ofwat-to-water-supply-v1` crosswalk. It rejects other sheets, changed headers,
formulas, unknown value states, duplicate facts and non-numeric reported values. It
never matches company names approximately.

```bash
uv run --locked watergeo-prepare-company-performance \
  official-wcpr.xlsx \
  --dictionary official-wcpr-data-dictionary.csv \
  --review docs/data-sources/ofwat-company-performance-2024-25-review.json \
  --output-root data/raw/operator-reviewed
```

The resulting `company-performance.json` records SHA-256 hashes of the exact workbook,
dictionary and review contract, then passes through the same normalizer and evidence
manifest used by ingestion. Numeric zero remains reported zero; blank values and `N/A`
become distinct states. The command checks its complete summary against the reviewed
contract before it can create validated evidence.

The official workbook contains 38,128 rows. WaterGeo's numeric company-performance
product accepts 35,381 rows: 20,952 reported numeric values, including 6,118 zeroes;
14,426 missing values; and 3 not-applicable values. They cover 21 company identities,
8 reporting periods and 243 measures.

The contract rejects 2,747 rows explicitly and records every reason: 2,520 `Text` rows
that the numeric canonical product cannot represent, 170 rows without an official short
description, 13 CPIH index rows whose company identity is `-`, and 44 reviewed
nonnumeric tokens in otherwise numeric measures. These rows are not loaded or presented
as accepted company-performance facts. Any new token, source hash, header, summary or
formula fails the whole preparation instead of being silently discarded.
