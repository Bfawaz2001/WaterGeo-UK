# 0006: Exact reviewed WGS84 presentation for four water-supply areas

- Status: accepted
- Date: 2026-09-18
- Builds on: ADR 0004 and ADR 0005
- Scope: presentation only; canonical ingestion and point queries are unchanged

## Evidence

The repeatable read-only assessment scanned all **1,141** canonical areas. Plain
`ST_Transform(geom, 4326)`, ring orientation and 15-decimal GeoJSON serialization
yielded **1,137 valid representations and four invalid representations**: IDs
**3, 4, 16 and 21**. No baseline representation exceeded the 8 MiB API limit.
Their canonical EPSG:27700 geometries are valid. The failure is not resolved by
increasing decimal precision (ADR 0005).

The [machine-readable evidence](../data-sources/ofwat-water-supply-presentation-assessment.json)
records canonical and output hashes, validity reasons, types, holes, vertices,
bytes, area changes, round-trip symmetric differences, discrete boundary Hausdorff
distances, component correspondence and runtime versions. Repeated independent
runs produced identical candidate WKB and GeoJSON hashes. Source provenance and
the unidentified OGL edition are retained in that evidence.

The measured environment was PostgreSQL 17.11, PostGIS 3.6.4, PostGIS GEOS 3.11.1,
and PROJ 9.8.1 with network access disabled. Offline boundary-distance and candidate
comparisons used Shapely 2.1.2 / GEOS 3.13.1. These two GEOS runtimes must not be
confused: candidate construction and serialization were performed in PostGIS.

### Candidate comparison

| ID | Canonical parts | Structure parts | Linework parts | Holes before/after | Structure round-trip symmetric difference (m²) | Structure boundary Hausdorff (m) |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| 3 | 2 | 3 | 3 | 41 / 41 | 438.730578 | 0.001016381 |
| 4 | 607 | 607 | 608 | 189 / 189 | 2084.500843 | 0.001035258 |
| 16 | 11 | 12 | 12 | 47 / 47 | 421.908493 | 0.001041711 |
| 21 | 66 | 67 | 67 | 0 / 0 | 57.045218 | 0.000994423 |

All three repair candidates (`linework`, `structure keepcollapsed=true` and
`structure keepcollapsed=false`) returned valid, nonempty MultiPolygons with no
lower-dimensional components. Structure keep/drop gave identical outputs. Holes
were retained, but polygon components are **not** unchanged: IDs 3, 16 and 21 gain
one part. That change is explicitly accepted for these presentation outputs only.

Structure and linework are topologically equal for IDs 3, 16 and 21. For ID 4,
structure retains 607 parts while linework creates 608. Their round-trip symmetric
difference is approximately 1.42e-14 m² and discrete boundary Hausdorff difference
is approximately 0.000140216 m. Structure is the preferred candidate among those
assessed: it ties the other repairs on the measured distortion of three areas and
avoids linework's additional tiny component in area 4. This is not a claim that
every possible transformation has been evaluated.

Structure round-trip signed area changes are approximately +4.881866, +30.562004,
+4.831586 and +0.013251 m² respectively. Round-trip area/distance measurements
include projection and serialization effects, not just repair effects. For
example, plain reprojection already produces 438.728327 m² symmetric difference
for ID 3 and 2084.500843 m² for ID 4 after returning to BNG. Do not interpret the
table's entire symmetric difference as land added/removed by the repair.

The metric is **symmetric discrete Hausdorff on boundaries at existing vertices**,
with distances to indexed target segments. It is not an exact continuous
Hausdorff bound or a geodetic accuracy claim. Tests compare it to GEOS's discrete
boundary metric. Invalid round trips have null area/symmetric-difference metrics;
an explicitly labelled untrusted signed area is retained for diagnosis. They are
not silently repaired just to obtain a measurement.

Component correspondence uses polygon intersections after the round trip. A tiny
part moved by datum round-trip error may no longer intersect its original; these
counts are not proof of semantic component identity or of deleted land. This
effect is already observed in area 4's unrepaired baseline. Exact output hashes,
explicit part/hole counts and the measured comparisons define this review.

### Densification rejected as a general policy

Source segmentization at 100 m and 10 m makes ID 4 valid but leaves 3, 16 and 21
invalid. At 10 m, ID 4's GeoJSON exceeds 8 MiB. The preliminary 1 m experiment
produced 3,434,615 vertices for ID 4 and was invalid again. The bounded assessment
therefore records that candidate as skipped under its one-million-vertex budget;
it does not claim a complete set of measurements for that oversized candidate.
Other measured 1 m candidates remain invalid and greatly increase payloads.
No densification is introduced into the API or canonical dataset.

## Presentation decision

Introduce a policy separate from the canonical transformation:

```text
canonical:    ofwat-water-supply-v1_5-structure-v1
presentation: ofwat-water-supply-v1_5-wgs84-structure-v1
```

For exactly the reviewed archive SHA-256 and canonical transformation version,
apply the following presentation expression only when both the source ID and
canonical little-endian WKB SHA-256 match the four-entry contract in
`src/watergeo/core/presentation.py`:

```sql
ST_MakeValid(ST_Transform(geom, 4326), 'method=structure keepcollapsed=false')
```

Only unreviewed IDs follow plain `ST_Transform`. For reviewed exception IDs,
failure to match the exact canonical hash or dataset identity is an error: return
the generic 503 without falling back to ordinary reprojection. Both paths then
orient polygon rings, serialize at 15 decimal places, enforce the 8 MiB bound and reparse/validate
the representation. A repaired output must also match its **exact reviewed
GeoJSON SHA-256**. A mismatch returns the existing generic 503; there is no fallback
repair, precision reduction, filtering, simplification or new tolerance.

This content guard deliberately fails closed if changed PostGIS/GEOS/PROJ data
or serialization produces different output, even if it is valid. Runtime version
names alone do not prove identical grid data or coordinates. A changed output
requires another assessment and presentation version; do not update hashes merely
to make a failing request pass. The normal path still requires valid output for
all unreviewed areas. Synthetic tests prove that matching geometry under an
unreviewed ID does not acquire an exception.

No rows are inserted or updated. Canonical geometry, source fields, ingestion
transformation records, their hashes and their five approved source IDs remain
unchanged. Point queries continue to use canonical BNG geometry; presentation is
not an alternative supplier-lookup dataset. No migration, grant or dependency
change is required. Existing timeouts and read-only runtime identity remain.

## Public provenance

Dataset metadata adds `presentation_version`, `presentation_review_reference`
and `presentation_exception_source_ids`. Its existing `transformation_version`
continues to mean canonical ingestion.

GeoJSON Features add a `presentation` foreign member with policy version,
`method` (`reprojection` or `post_transform_structure`), review reference, output
CRS/precision and a GeoJSON hash. The reviewed canonical WKB hash is included only
when the exception is applied. `canonical_geometry_changed` is always false.
The original `properties.transformation` still describes canonical ingestion.

The GeoJSON hash is over **PostGIS's oriented 15-decimal geometry text**, before
FastAPI parses and serializes the response. It is not a checksum of the complete
HTTP body or of a client's differently formatted JSON. `hash_encoding` makes
that distinction explicit. The underlying source licence remains OGL with an
unidentified edition; neither this ADR nor the code licence changes that.

## Verification

- Baseline scan: 1,141 areas, exact failure set 3/4/16/21.
- Repeated assessment: identical candidate hashes and recorded runtime versions.
- Canonical row digest before/after, including complete source fields and EWKB:
  `529e2105187a4d366a4f83f82a1e08eef63bb65a7215ec7ba0aadc74dd1d3801`.
  The final digest uses a fresh transaction, not only the repeatable-read snapshot.
- Real-data HTTP verification with the normal three-second statement timeout:
  **1,141 HTTP 200 responses**, each a valid MultiPolygon after response parsing;
  exceptions only for 3/4/16/21, canonical digest unchanged.
- Disposable synthetic PostGIS tests exercise projection-induced invalidity,
  policy application, input/output hash mismatches, unreviewed IDs, separate
  provenance, full baseline discovery, candidate repeatability and vertex budgets.
- CI uses invented geometries and never downloads the real source archive.

References: [ST_MakeValid](https://postgis.net/docs/ST_MakeValid.html),
[ST_Transform](https://postgis.net/docs/ST_Transform.html),
[ST_Segmentize](https://postgis.net/docs/ST_Segmentize.html),
[ST_HausdorffDistance](https://postgis.net/docs/ST_HausdorffDistance.html),
[Shapely STRtree](https://shapely.readthedocs.io/en/stable/strtree.html).
