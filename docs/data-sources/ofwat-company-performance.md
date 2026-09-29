# Ofwat company performance

## Accepted publications

- [Water Company Performance Report 2024–25 machine-readable data](https://www.ofwat.gov.uk/publication/data-for-the-water-company-performance-report-2024-25-open-data-friendly-machine-readable-format/).
- [PR24 historical performance trends V6.0](https://www.ofwat.gov.uk/publication/historical-performance-trends-for-pr24-v6-0/), published 15 January 2026 and covering data through 2024–25.
- **Publisher/licence:** Ofwat, Open Government Licence 3.0.

The WaterGeo preparation contract records the exact publication, publisher company identifier/name, reporting period, measure code/name, numeric value or explicit `missing` / `not_applicable` state, unit and definition/source metadata. Zero remains a reported numeric value. Regulatory facts are not recast as WaterGeo ratings.

## Boundary crosswalk

Company performance has no point geometry. It may attach to a selected water-supply area only through the reviewed `ofwat-to-water-supply-v1` crosswalk included in accepted evidence. The normalizer rejects row-level mapping fields and unknown crosswalk versions. Mapping is by exact publisher/company identity to the exact boundary acronym; no fuzzy company-name join occurs. Unmapped companies remain unmapped.

Ofwat editions are publication-driven. There is no polling workflow. The bounded
`watergeo-prepare-company-performance` command converts an operator-supplied official
XLSX file into a validated Phase 15 evidence bundle. It requires a reviewed JSON
contract that names the exact worksheet, maps every required field to an exact header,
declares the missing and not-applicable vocabularies, and contains the exact
`ofwat-to-water-supply-v1` crosswalk. It rejects other sheets, changed headers,
formulas, unknown value states, duplicate facts and non-numeric reported values. It
never matches company names approximately.

```bash
uv run --locked watergeo-prepare-company-performance \
  official-wcpr.xlsx \
  --review reviewed-wcpr-2024-25.json \
  --output-root data/raw/operator-reviewed
```

The resulting `company-performance.json` records SHA-256 hashes of the exact workbook
and review contract, then passes through the same normalizer and evidence manifest used
by ingestion. Numeric zero remains reported zero; configured missing and N/A tokens
become distinct states. The command reports company, period, measure, row, missing,
N/A and rejected counts.

The official Ofwat publication page confirms a 1.42 MB machine-readable 2024–25 file.
Local searches in `~/Downloads`, `~/Downloads/WaterGeo-Phase16B` and `~/Desktop` found
neither that workbook nor its data dictionary. The single bounded official retrieval
attempt on 29 September 2026 returned HTTP 403. No unofficial mirror was used.

The worksheet, headers, value vocabularies and row counts therefore remain unverified,
and WaterGeo has not accepted this edition. An operator must manually download both
official files from the links above, inspect the workbook and dictionary, create and
review the exact JSON contract and crosswalk, run the command, and independently review
its summary and generated JSON. WaterGeo does not guess those meanings or claim a real
accepted row count.
