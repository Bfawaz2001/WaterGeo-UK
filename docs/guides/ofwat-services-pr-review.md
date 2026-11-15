# Unified Ofwat service-boundaries pre-PR review

Reviewed 15 November 2026. Starting commit: `72814b1`, branch
`feat/unified-ofwat-service-boundaries`.

## Findings resolved before opening the PR

- Added standalone `validation-report.json` to the local bundle, protected by the
  manifest's payload checksum. Existing `final-v1` artifacts were retained without
  modification; the reviewed example is the new `final-v2` edition.
- Strengthened semantic validation across source layers, typed dimensions, service
  and snapshot identities, company mappings, bridge review references and browser
  indexes. Quarantine flags in dimensions must exactly match source-layer rows.
- Required a valid external manifest pin when explicitly supplied, closing an
  empty-string fallback in the Fabric import path.
- Added negative tests for re-signed inconsistent joins, unapproved geometry
  policy, silently repaired quarantined geometry, malformed coverage dimensions,
  validation-report drift and corrupted files. The Fabric tests verify rejection
  before any Spark Parquet read.
- Required exact company geometry feature count; an inventory matching only a
  response prefix is insufficient.

## Final artifact review

[ZIP audit evidence](../data-sources/ofwat-service-zip-review.json) records the ZIP
and manifest hashes, all member counts and original-source comparisons. The ZIP
has 1,904 members: 1,902 checksummed payloads plus the manifest and its SHA-256 file.
It contains both full GeoParquet and GeoJSON layers, per-area GeoJSON, overviews,
25 company dimension rows, two service rows, 1,889 area rows, 1,889 reviewed bridge
rows, the original mapping review and a standalone validation report.

All 1,889 source features match fresh decodes of the two fingerprint-pinned public
archives, including exact original WKB and all publisher attributes. Quarantined
source IDs remain water supply 1/4/6/28/30 and sewerage 11. None is coverage-eligible.
These are retained source artifacts, not an approval of invalid geometry or a new
canonical repair. There is no complete valid-coverage claim.

## Governance and remaining remediation

The full export input comparison establishes the two public Parliament archives
and reviewed public company-label mappings as the dataset inputs. There are 17
original publisher fields and no PCD/property/address inputs. Changed and untracked
text files were reviewed and scanned for private keys, GitHub/AWS tokens, Azure
SAS links, Fabric workspace URLs and tenant/workspace secret assignments. No
matches were found. No ZIP/Parquet/GeoJSON, `.env`, private key or credential file
is staged for the PR. Generated datasets, builds and credentials remain ignored.
Generic Lakehouse paths in the notebook are examples, not tenant identifiers.

A repeat read-only local API scan reproduced 20 successful company views and four
fail-closed 503s (AFW/ANH/SBB/SEW). Canonical and presentation verification policy
files and server geometry guards are unchanged. The operational remedy is in the
[separate runtime remediation guide](ofwat-company-runtime-remediation.md). No
runtime, database, approved geometry hashes or deployment was changed.

## Final tests

- Ruff lint/format and mypy: pass.
- Python non-integration suite: **770 passed**, 150 integration tests deselected.
- Frontend lint/typecheck: pass; **165** unit tests passed.
- Existing browser suite: **12** passed, including historical Hydrology workflows.
- Static-publication browser suite: **3** passed.
- Wheel/source distribution: built successfully.
- Local ZIP: CRC, payload/manifest checksums, typed schemas, joins, quarantine and
  exact public-source WKB/attribute comparisons pass.

No database migrations or writes were introduced, so the opt-in database
integration suite was not run locally. CI retains its existing disposable
integration jobs. No real Fabric tenant was accessed; Spark behavior is exercised
with a local test double. Optional PMTiles were not generated in the example.

## Reviewer reproduction

Use the [Fabric/export walkthrough](ofwat-services-fabric.md) to build a local
bundle. Reproduce the audit with `scripts/review_ofwat_service_zip.py`, supplying
an externally recorded manifest hash. The example ZIP remains local and is neither
committed nor uploaded as a PR/release asset. PR workflows run tests and image
builds; Pages publication and dataset refresh require separate explicit workflow
invocation. Do not merge, deploy, refresh or publish as part of this review.
