# Ofwat service export and Fabric import walkthrough

This workflow builds a portable bundle locally. It makes no connection to a real
Fabric tenant. PCD is not an input. Use the
[architecture and acceptance policy](../architecture/unified-ofwat-services.md)
to understand the quarantined publisher geometries before spatial analysis.

## Build and validate locally

From the repository root, install the locked exports extra:

```sh
uv sync --locked --extra exports
```

Fetch the two pinned official archives into ignored local storage and build a new
edition. The downloader rejects unexpected fingerprints, sizes, schemas and
metadata; do not change expected hashes just to accept a newer download.

```sh
uv run --locked python -m watergeo.service_boundaries \
  --fetch --output data/exports/ofwat-services-april2024-v1
```

To reuse already verified `data/raw/ofwat/water-supply/` and
`data/raw/ofwat/sewerage/` archives/manifests, omit `--fetch`. The existing exporter
also supports the new product:

```sh
uv run --locked watergeo-export --entity ofwat-services \
  --output data/exports/ofwat-services-april2024-v2
```

Both commands always produce both GeoParquet files and all dimensions. Optional
PMTiles require Tippecanoe with PMTiles output support; add
`--tippecanoe /absolute/path/to/tippecanoe`. Those files are display derivatives.
They do not change source geometry or coverage eligibility.

```sh
uv run --locked python -m watergeo.service_boundaries \
  --validate-only --output data/exports/ofwat-services-april2024-v1
uv run --locked python scripts/assess_ofwat_sewerage.py \
  --output /tmp/ofwat-sewerage-assessment.json
```

Validation checks payload sizes/hashes, independent source snapshots, CRS,
source counts/IDs, geometry types, invalid geometry IDs, licence fields, reviewed
company mappings, bridge completeness, exact source WKB and recorded presentation WKB hashes after GeoJSON
round trips. It does not recompute projection in the consumer runtime. Keep `manifest.sha256` separately to pin an edition. For stronger
transfer integrity pass that externally recorded digest directly:

```python
from pathlib import Path
from watergeo.service_boundaries import validate_service_bundle

manifest = validate_service_bundle(
    Path("data/exports/ofwat-services-april2024-v1"),
    expected_manifest_sha256="<externally recorded SHA-256>",
)
```

Full-source exports contain six invalid publisher geometries: five water-supply
features and sewerage ID 11. They remain available for inspection, with
`source_valid=false`, reason text and `coverage_eligible=false`. A successful
bundle validation means the **recorded source anomalies** match; it does not mean
every publisher polygon is valid. Do not call a valid-only subset complete
coverage. The existing approved canonical water-supply API product remains separate.

## Preview the optional service browser

The browser is opt-in so existing static publications continue to work. Serve the
bundle from a same-origin directory such as `/service-boundaries` and configure:

```text
VITE_WATERGEO_SERVICE_BUNDLE_PATH=/service-boundaries
VITE_WATERGEO_SERVICE_MANIFEST_SHA256=<digest from the reviewed manifest.sha256>
```

Set these at Vite build time, or when running the local Vite server. For local
preview only, copy the bundle into `web/public/service-boundaries/` and run the
frontend; this directory is ignored by Git. Do not commit or deploy those files
without a separate publication review. No public source manifest or deployment
workflow is changed by this phase.

The service selector switches independently between water and sewerage inventories.
Each undertaker shows every associated source area, a simplified outline overview,
quarantine counts, exact original attributes and a checksum-verified individual
GeoJSON download. Keep the primary analytical GeoParquet files for analysis.

## Import into a consumer-owned Fabric workspace

1. In your own dedicated Fabric workspace, create or choose a Lakehouse and attach
   it as the notebook's default Lakehouse. WaterGeo does not provision these objects.
2. Upload the **entire** bundle, without renaming its payload files, to
   `Files/watergeo/ofwat-services/april-2024-v1/`. Keep a separate reviewed copy of
   the manifest digest. The validation cells inspect all files, including individual
   GeoJSON features, so a partial upload is rejected.
3. Build the reviewed WaterGeo wheel (`uv build`) and install it with its `exports`
   extra into the notebook environment using your workspace's package mechanism.
   The package requires Python 3.12 or newer; use a compatible Fabric environment.
   Do not install from an unreviewed branch or assume WaterGeo is published on PyPI.
4. Copy the cells from
   [`examples/fabric/ofwat_services_notebook.py`](../../examples/fabric/ofwat_services_notebook.py).
   Call `read_services(spark, "april-2024-v1", "<recorded manifest hash>")`.
5. Inspect counts (1,141 / 748), the six quarantine flags, the nullable OGL edition,
   company dimensions, bridge and snapshot identities before analysis. Join
   dimensions on `boundary_id` / `company_id`, retaining service and snapshot.
   Never join water and sewerage on `source_id` alone.
6. Optionally call `save_delta_tables(bundle, "ofwat_april2024_v1")`. This explicitly
   creates six tables in the attached consumer-owned Lakehouse. Existing tables
   cause an error; it never overwrites them. Tables commit separately, so use a new
   prefix if an interrupted run leaves partial tables.

Spark reads the geometry column as **binary WKB**. Keep it binary. Coordinates are
British National Grid metres (EPSG:27700), not longitude/latitude. The example
adds the source CRS and manifest hash as Delta columns and keeps all source
provenance columns. It does not assume Spark has a spatial extension installed.
Any later spatial-library use must explicitly declare CRS and exclude quarantined
geometry while reporting that coverage is incomplete.

GeoParquet carries its CRS in the `geo` schema metadata; Spark/Delta may not retain
that file-level metadata. The original GeoParquet and immutable manifest therefore
remain the geometry/provenance authority in Lakehouse **Files**, alongside optional
Delta tables. Do not replace the original files with a text or SQL-geometry export.

No Fabric execution or tenant validation is claimed. The walkthrough is an
explicit consumer import procedure, supported by local geometry/relational/file
validation. No internal Ofwat/PCD data is present or accessed.

## Recorded local verification

The complete [example evidence](../data-sources/ofwat-service-export-validation.json)
records 1,889 rows, 25 reviewed company groups, 1,889 bridge rows and every layer's
checksums. The ignored local example is `data/exports/ofwat-services-final-v2/`.
Its externally pinnable manifest digest appears in that evidence report.

Verification completed on 15 November 2026:

| Check | Result |
| --- | --- |
| `ruff check .` / `ruff format --check .` | Pass |
| `mypy src` | Pass, 105 source files |
| `pytest -m 'not integration'` | 770 passed; 150 integration tests deselected |
| Frontend lint / typecheck | Pass |
| `npm test -- --run` | 165 passed |
| `npm run test:e2e` | 12 passed, including historical Hydrology |
| `npm run test:e2e:static` | 3 passed |
| `uv build` | Wheel and source distribution built |
| Real-source bundle validator | All 1,889 feature / geometry / bridge records verified |
| Sewerage assessment reproduction | Byte-identical diagnostic JSON |
| Local real-bundle Chromium preview | Leep water (109 areas), Wessex sewerage (3 areas, ID 11 flagged), verified area download; no page errors |

Database integration tests were not run: this phase has no migrations or database
writes. The existing local database was queried read-only to diagnose runtime drift.
Optional PMTiles and real Fabric execution were not run. The full local ZIP is
`data/exports/ofwat-services-final-v2.zip`; its sibling `.zip.sha256` records the
outer archive checksum. The ZIP contains the manifest and every bundle payload.

## Pre-PR review hardening

The original `72814b1` local ZIP is retained unchanged. The reviewed `final-v2`
edition supersedes it and adds a standalone, checksummed `validation-report.json`.
The validator cross-checks every area dimension and quarantine flag against the
source layer, every service/snapshot key, all bridge review references, typed
schemas and browser-index relations. The Fabric example requires a nonempty
externally pinned SHA-256 before any Spark read. Negative tests reject corrupted
files, inconsistent joins and a silently repaired quarantined geometry, even when
payload hashes and the manifest are recomputed for the test.

Reproduce the ZIP audit (the digest is recorded in the evidence JSON):

```sh
uv run --locked python scripts/review_ofwat_service_zip.py \
  --zip data/exports/ofwat-services-final-v2.zip \
  --manifest-sha256 <reviewed-manifest-sha256> \
  --output /tmp/ofwat-service-zip-review.json
```

The [ZIP review evidence](../data-sources/ofwat-service-zip-review.json) compares
all source WKB and publisher attributes to fresh decodes of the two exact public
archives. Known company presentation failures have a
[separate remediation guide](ofwat-company-runtime-remediation.md); the verification
gate stays in place. No bundle ZIP, downloaded geometry, credential file or
workspace-specific configuration is committed or attached to the PR.
