# 0004: Ofwat water-supply v1.5 canonical transformation

- Status: accepted
- Date: 2026-09-18
- Source SHA-256: `5852ec4481af0ab27e43a2d0d142ca0b55b7a4415eedf68ebe2a20a21fe41f78`
- Related: ADR 0002, ADR 0003, PR #10

## Context

The reviewed Ofwat water-supply boundary release contains 1,141 features in
EPSG:27700. Exactly five publisher geometries are invalid:

`1, 4, 6, 28, 30`

All five fail because of self-intersection.

ADR 0003 prohibits silent geometry repair. PR #10 assessed the actual publisher
geometries using three candidate transformations:

- `make_valid(method="linework", keep_collapsed=True)`
- `make_valid(method="structure", keep_collapsed=True)`
- `make_valid(method="structure", keep_collapsed=False)`

The assessment used Shapely 2.1.2 and GEOS 3.13.1.

For IDs 1, 4, 28 and 30 all three candidates were topologically equivalent.

ID 6 was the only divergence. Linework retained an additional near-degenerate
polygon with approximately `9.75969936439e-10 m²` area. Both structure variants
produced the same 16-part result.

## Decision

For this exact archive only, WaterGeo UK accepts:

`method="structure", keep_collapsed=False`

Transformation version:

`ofwat-water-supply-v1_5-structure-v1`

It is approved only for source IDs:

`1, 4, 6, 28, 30`

This is not a generic invalid-geometry rule.

Valid publisher geometry passes through unchanged except that Polygon may be
wrapped as MultiPolygon for the canonical database type.

No reprojection, simplification, snapping, rounding, buffering, coordinate
editing, component filtering or feature deletion is permitted.

## Fail-closed geometry contract

Canonical ingestion verifies:

1. exact archive SHA-256;
2. exact source ID;
3. decoded source WKB SHA-256;
4. Shapely 2.1.2;
5. GEOS 3.13.1;
6. approved algorithm and parameters;
7. resulting canonical WKB SHA-256;
8. expected geometry type and part count.

| ID | Source WKB SHA-256 | Canonical WKB SHA-256 | Parts |
|---:|---|---|---:|
| 1 | `084a7f2d30e6e084f0037b2eae63de4a9478d111d30dc9e3494477b530eaa0a3` | `8939d2cf392d8b7d9f37b88df7492012cae16f9118db4a152303f459588c2a7f` | 3 |
| 4 | `0a8de1f1dcc91a2edf60d2238b092681199a1c0b854e44dbb8b59a573bb180aa` | `829928770402be6b318f86cf9e9e28212c8d8f6314071db89c3de39e6d01a4a3` | 607 |
| 6 | `8d12dac0f45ab63fa44c93e7770965e3cdf47d760cd125d80dd6d7301782e8fa` | `2a311f09afd4e3aeb3cff8f6b22945514875e680159f524715ba6d183ed06745` | 16 |
| 28 | `a8d8f564a29d4452afad516c59057253eadf5c888ead89daf17db6a9f0970a7d` | `58ed9a8dad021a0d35ff6eeb5fb74310eacc232825ea839187c3d8f1609dd7bc` | 12 |
| 30 | `4027a26bfb570327bd6866e752a74042c5db673e680366306acc44d2b8ee9364` | `d9afd2c91284e189be0f4befdb1049a695f0738c48297990f17308ad3f9db337` | 2 |

Any source, dependency or output change requires another assessment and a new
transformation version.

## Provenance

The raw ZIP remains the authoritative publisher artifact.

WaterGeo transformation metadata is stored separately from publisher
`source_fields`. Each transformed feature records the source and canonical WKB
hashes, algorithm, parameters, runtime versions, validity reason, assessment
version and ADR reference.

## Licence and publisher metadata

Every one of the 1,141 publisher records states:

> This shapefile is published under the Open Government Licence.

The source does not identify an OGL edition. `licence_version` therefore remains
NULL.

The publisher provenance, licence text and disclaimers remain verbatim in each
area's `source_fields`.

## Atomicity

Canonical ingestion inserts in one transaction:

- one snapshot;
- exactly 1,141 area records;
- exactly five transformation-provenance records.

Any validation, transformation, geometry, provenance, count or database failure
aborts the complete load.

Loading the same SHA-256 and transformation version again is a verified no-op.

## Scope

This decision applies only to Ofwat water-supply release v1.5 with SHA-256:

`5852ec4481af0ab27e43a2d0d142ca0b55b7a4415eedf68ebe2a20a21fe41f78`

The canonical result is a reviewed WaterGeo transformation for geospatial use.
It is not a replacement for the definitive legal record.
