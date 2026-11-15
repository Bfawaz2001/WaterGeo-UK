# Unified Ofwat service-boundary product

Implemented on `feat/unified-ofwat-service-boundaries`, based on Phase 18B.1
`bca9fcc`. Source and company-label review: 14 November 2026.

## Architecture and acceptance decision

The portable product is an additive, source-preserving export, independent of the
PostGIS application and any Fabric tenant. Each service has its own content-addressed
raw archive, retrieval manifest and validation contract. Snapshot identity is the
archive SHA-256. Area identity is `dataset:archive_sha256:source_id`. An area is never
identified by a source ID alone, nor assumed continuous between releases.

The original ZIP is authoritative. GeoParquet contains unmodified decoded publisher
WKB in EPSG:27700, preserving Polygon/MultiPolygon types. Individual features are
never dissolved, clipped, simplified or repaired in these analytical files.
`source_fields_json` retains all 17 publisher fields, including source licence,
disclaimers, provenance, dates and warnings. Null grant dates represent source
`00000000`; retain the raw ZIP to recover original DBF bytes and field encodings.
Every row carries the composite identity, dataset, service, snapshot fingerprint,
source/presentation WKB hashes, reviewed company group and review reference.

Acceptance has two explicit levels:

1. **Verified publisher snapshot:** exact bytes/hash, archive/schema/CRS, IDs, counts,
   dates, notices and the recorded invalid-geometry set all match. This authorises
   the source-preserving product including flagged invalid features.
2. **Coverage-eligible source feature:** valid, nonempty publisher polygon. Invalid
   features are retained with `coverage_eligible=false`. They must be filtered from
   spatial operations, and their omission must be disclosed as incomplete coverage.

This does not approve a new canonical repair. Water supply's existing PostGIS
canonical and WGS84 presentation contracts remain governed by ADRs 0004/0006.
Their five repaired source features are deliberately still invalid **source**
features in this source product. Consumers needing that accepted water-supply
presentation product can continue to use the existing API export. Do not substitute
source-product rows for canonical API storage.

Sewerage ID 11 remains quarantined. The reproducible
[assessment](../data-sources/ofwat-sewerage-geometry-assessment.json) confirms nested
holes. Linework and structure candidates differ by about `8.7134e-11 m²` symmetric
difference and `58.3358 m` Hausdorff distance. Structure variants agree, but these
metrics do not establish publisher intent. No candidate is approved or applied.
A future canonical sewerage load requires a separately reviewed transformation
contract with archive, input WKB, runtime, algorithm and output WKB fingerprints.

## Source acceptance

| Service | Archive release | Rows | Polygon / MultiPolygon | Invalid source IDs |
| --- | --- | ---: | --- | --- |
| Water supply | v1_5 | 1,141 | 1,086 / 55 | 1, 4, 6, 28, 30 |
| Sewerage | v1_5a | 748 | 711 / 37 | 11 |

The [source assessment](../data-sources/ofwat-company-boundaries.md) records exact
URLs, sizes, archive fingerprints, HTTP metadata and source caveats. The official
[Commons page](https://commonslibrary.parliament.uk/research-briefings/cbp-10541/)
was checked again on 14 November 2026: April 2024 v1_5 downloads remain linked and
both services are declared OGL. Archive suffix `v1_5a` differs from sewerage record
`Version=1_5`; these are retained separately. Both source `LastUpdate` dates are
2024-04-25. Neither is an assertion of current coverage.

All source rows have the same explicit OGL statement. The edition is unspecified;
`licence_version` is a typed nullable string and remains null. This extends the
source-preservation treatment recorded in ADR 0004, not a claim of OGL v3. Source
and data rights remain distinct from the repository MIT licence. Project attribution
credits Ofwat, Commons Library and Ordnance Survey support, without asserting
publisher endorsement or inventing OS licence numbers.

Service derives exclusively from archive membership. Contradictory `AreaType`
labels remain verbatim. NAV/inset rows remain individual records. No topology-wide
overlap/gap assessment, legal-record comparison or completeness/currentness claim
is made. Missing mappings, changed source hashes, geometry anomalies or dates fail
before any output edition becomes visible.

## Company mapping

The [crosswalk](../data-sources/ofwat-service-company-crosswalk.json) explicitly lists
all 48 observed `(dataset, COMPANY, Acronym)` tuples. It groups historical publisher
labels, not current registered legal entities. The project `company_id` values are
reviewed analytical group identifiers, independent of performance-product keys.
Do not join them to company-performance IDs by spelling or derive legal identity
from a name/acronym.

Leep's explicit “formerly Peel” and “formerly SSE” labels are grouped with Leep;
LWS, PWN and SSE remain original attributes. Severn Trent Services (STS) stays
separate from Severn Trent Water (SVE). All other mappings retain their exact named
publisher group. There are 25 company groups across the two services. Every area
must map exactly once; unknown/duplicate tuples fail closed. Changing this review
file changes its recorded SHA-256 and requires a new bundle edition. The bridge
retains the service, snapshot, composite boundary ID, company ID and review reference.

These dimensions are suitable for a **later reviewed join**. There is no postcode,
property or PCD adapter, fixture, join key inference or internal Ofwat data in this
phase. A `pcd_included=false` manifest value describes this product's inputs; it is
not a substitute for reviewing any future inputs.

## Geometry and delivery

| Artifact | Geometry / purpose |
| --- | --- |
| `water-supply.parquet`, `sewerage.parquet` | GeoParquet 1.1, original decoded WKB, explicit EPSG:27700 PROJJSON |
| `water-supply.geojson`, `sewerage.geojson` | Full individual source features reprojected to CRS84; validity flags retained |
| `areas/<service>/<id>.geojson` | Same per-feature GeoJSON for bounded retrieval |
| `<service>-overview.geojson` | Display-only, topology-preserving simplification with 0.001° tolerance; no repair |
| Optional `<service>.pmtiles` | Overview-only tiled derivative; clipping/quantisation/simplification permitted |
| `companies.parquet`, `services.parquet`, `areas.parquet` | Explicit Arrow string/int64/bool dimension columns; nested publisher fields as JSON |
| `company-area-bridge.parquet` | Reviewed complete company-to-area relation |
| `index.json`, `company-crosswalk.json` | Browser inventory and exact mapping review |
| `validation-report.json` | Standalone source-validation reports and geometry/quarantine counts |
| `manifest.json`, `manifest.sha256` | Sources, counts, CRS, runtime, validation, attribution, file hashes/bytes and manifest digest |

GeoJSON uses PyProj `always_xy=True`, `allow_ballpark=False`; the runtime and
transformation description are recorded. It is a **reprojected source** product,
not ADR 0006 presentation output. Validity is measured again after reprojection;
invalid projected geometries remain flagged and must not be used for coverage.
The browser's simplified overview draws outlines, including invalid source rings,
without treating them as valid coverage. No company-level dissolved geometry
replaces individual features.

A new output directory is staged, validated and renamed only on success. Existing
editions are rejected. The manifest lists every payload checksum and byte count;
its separate hash can be pinned externally. This is integrity evidence, not a
publisher signature or a filesystem write-protection mechanism. Never overwrite
an issued edition; rebuilding uses a new directory.

## Explorer and whole-company diagnosis

The existing company endpoint has an 8 MiB total collection limit; individual
features also have an 8 MiB limit. The browser separately caps JSON at 10 MiB.
Large companies can therefore fail even when every individual geometry meets its
verification contract. Inventory and geometry failures previously shared one
message, obscuring this cause.

The existing explorer now falls back **only on size failures** to requests for
individual, snapshot-pinned features in batches of four. It checks ordered IDs,
feature snapshots, company acronyms, uniqueness and complete inventory counts
before displaying any collection. Geometry validation failures (503) remain
failures. Transport limits stay in place.

The optional service browser reads the portable bundle through a same-origin path
and an externally pinned manifest hash. It verifies the inventory/overview/area
file checksums, bytes and composite identities, offers independent service and
company selections, shows all associated insets, and discloses quarantine flags,
publisher attributes and attribution. It uses a separate simplified outline view;
it does not change existing map selection, source status or Hydrology history.
Whole layers are intentionally downloadable analytical artifacts; the browser does
not load the 52 MB / 39 MB full GeoJSON layers as a response.

### Local runtime diagnosis, 15 November 2026

A [read-only scan](../data-sources/ofwat-company-runtime-diagnosis.json) of all
24 company geometry endpoints returned 20 HTTP 200 and four HTTP 503 responses:
AFW, ANH, SBB and SEW. No HTTP 413 was observed in this baseline scan. The four
reviewed presentation exceptions (source IDs 3/4/16/21) retain the correct canonical
WKB fingerprints, but their WGS84 hashes are outside every approved variant.
The local database reports PostGIS 3.7.0, GEOS 3.15.0 and PROJ 9.9.0, plus core
procedures at 3.6.4 needing upgrade. This is runtime drift, not a missing company
mapping or a reason to bypass the content guard. Restore a consistent previously
reviewed runtime or undertake a separate presentation reassessment. This phase
does not upgrade the database, whitelist new hashes or reinterpret the API 503s.

The new source product is independently verified against its recorded local
Python runtime and does not claim to repair this canonical presentation deployment.
Its real sewerage Anglian group totals 9,701,968 bytes across individual GeoJSON
files, illustrating why a future sewerage collection endpoint also needs bounded
per-feature delivery. The synthetic large-company export test exceeds 8 MiB and
checks that both analytical layers and all bridge rows survive without truncation.

## Implementation phases and acceptance tests

1. Verify official metadata/fingerprints and add the separate sewerage contract.
   Reproduce its invalid geometry assessment without mutating the archive.
2. Export all source records with composite IDs, typed dimensions and explicit
   reviewed mappings. Stage and validate before exposing an immutable edition.
3. Add the optional service browser and bounded existing-company fallback.
4. Supply the Fabric consumer walkthrough, offline regression suite and real-source
   evidence report. No tenant connection, migration, publication or deployment.

Synthetic tests exercise colliding IDs across services/snapshots, both complete
source inventories, changed counts/invalid sets, mapping gaps/duplicates, snapshot
changes during export, immutable destinations, unknown licence edition, checksums
and exact source/presentation WKB hashes across file round trips. Frontend tests cover service selection, flagged
insets, hash corruption, size limits and a 413 fallback whose individual features
still fail closed on snapshot mismatch. Real-source evidence records the complete
1,889-feature round trip and large-company payload sizes. Optional PMTiles require
an installed Tippecanoe executable and an explicit flag.

## Reproduce the evidence

```sh
uv run --locked python scripts/validate_ofwat_service_example.py \
  --bundle data/exports/ofwat-services-final-v2 \
  --output /tmp/ofwat-service-export-validation.json
uv run --locked python scripts/diagnose_ofwat_companies.py \
  --base-url http://127.0.0.1:8000 --output /tmp/ofwat-company-responses.json
```

The recorded [export evidence](../data-sources/ofwat-service-export-validation.json)
pins the completed local example's manifest. Consumer validation checks stored
source WKB and presentation WKB hashes after GeoJSON decoding; it does not rerun
projection in the consumer's potentially different PROJ environment. The exporter
creates those presentation hashes directly from its actual projected geometries.
A pinned manifest therefore preserves the reviewed coordinates across transfers
without requiring consumers to reproduce a platform-specific datum transformation.

## Pre-PR review

The standalone report is a manifest-checksummed payload. Semantic validation also
checks typed dimension schemas, exact area properties/quarantine flags, service
snapshot keys, full bridge mappings/review references and browser inventory
consistency. An empty external manifest pin is rejected. Synthetic negative tests
re-sign deliberately inconsistent artifacts to prove these checks are independent
of transfer checksums. Known runtime drift remains an operational follow-up in the
[separate remediation guide](../guides/ofwat-company-runtime-remediation.md).
