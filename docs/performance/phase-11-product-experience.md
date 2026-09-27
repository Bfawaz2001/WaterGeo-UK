# Phase 11 product-experience measurements

Measured 2026-09-27 on the local Apple Silicon development workstation. Browser
figures are production Vite builds. Database figures use the disposable local
PostGIS service and describe development-machine latency, not a hosted service-level
objective.

## Search

The measured database held one compatible Water Quality snapshot with 66,300
sampling points. Searching the prefix `river` found 3,004 matching names; the public
response remained capped at 24 results and was 6,857 bytes.

The first plan exposed a sequential scan caused by the combination of an exact-ID
predicate and a name-prefix predicate. Migration `0011` now indexes normalized
identities and names for every searchable entity table. PostgreSQL then used a
`BitmapOr` over the Water Quality identity and name indexes. Across 30 warmed
TestClient requests, median end-to-end API time changed from 51.431 ms to 11.917 ms;
the largest corrected request was 13.371 ms. A cold `EXPLAIN ANALYZE` after recreating
the indexes took 49.782 ms and included disk reads, compared with 126.020 ms before
the identity indexes.

Search is prefix/identity based and does not call an external geocoder. It runs in a
repeatable-read transaction so results and source-availability metadata describe one
database view. Result selection then pins feature detail and geometry to the reported
snapshot.

## Production bundle

The Phase 10 baseline was rebuilt from commit `b91fa595` with the same installed Node
toolchain and compared with the Phase 11 production build.

| Asset | Phase 10 bytes | Phase 11 bytes | Change |
| --- | ---: | ---: | ---: |
| Initial application JS | 256,541 | 266,091 | +9,550 (+3.7%) |
| Lazy MapLibre/PMTiles JS | 1,048,929 | 1,050,798 | +1,869 (+0.2%) |
| Application CSS | 8,339 | 11,492 | +3,153 |
| MapLibre worker | 509,702 | 509,702 | unchanged |

Vite reported the initial JavaScript gzip size increasing from 78.53 kB to 80.85 kB.
MapLibre remains lazy-loaded. The search, accessible SVG trend chart and shell styles
stay in the initial application chunk because they are small and part of the primary
selection workflow.

## Map behavior

MapLibre clusters each enabled point source below zoom 11 and expands a selected
cluster using its native expansion zoom. Each source still contains at most the 100
server-bounded results for the current viewport. Cluster counts are therefore local
to those bounded results and are never presented as complete national totals. No
polygon layer is clustered, and the optional PMTiles overview behavior is unchanged.

Deterministic Playwright acceptance passed four production-build scenarios covering
search/detail timing, bounded map selection and provenance, API failure states, and
narrow-screen search/controls. No live publisher, public hosting or external map
service was used.
