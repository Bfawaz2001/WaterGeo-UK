# Phase 8 measured delivery results

Measured 2026-09-26 on the local Apple Silicon workstation. These are single-run
development observations, not production latency or mobile hardware guarantees.
Dataset: 1,141 reviewed Ofwat v1_5 areas, snapshot
`df81bca3-2583-4910-8aaf-beea87ef76ff`. Source archive SHA-256:
`5852ec4481af0ab27e43a2d0d142ca0b55b7a4415eedf68ebe2a20a21fe41f78`.

## Export comparison

| Artifact | Bytes | Meaning |
| --- | ---: | --- |
| National GeoJSON | 50,819,954 | All exact API geometries and properties |
| GeoParquet (Zstandard) | 18,390,361 | Same coordinates as WKB, provenance columns |
| PMTiles zoom 0–8 | 695,013 | Simplified overview; reduced attributes |

The full local export through TestClient/API/SDK, including 1,141 geometry requests,
completed in 24.36 seconds. Tippecanoe 2.79.0 compiled from official release commit
`68ab8dcc229f95b8b25877697d5e8d66783af503`; PyArrow 23.0.1. No database rows were
changed. The export manifest records exact artifact hashes and presentation policy.

`node web/scripts/measure-overview.mjs EXPORT_DIRECTORY` requested six zoom-five
positions (x=15,16; y=9,10,11), including header/metadata and directory reads. Three
tiles existed; five local reads totalled **73,333 bytes**, taking 58.57 ms including
decode. Parsing the full GeoJSON string took 339.70 ms after disk read. These timings
measure different work and must not be described as a rendering speedup. The useful
comparison is bytes delivered: the full archive is about 98.6% smaller than exact
national GeoJSON, while viewport reads need only a fraction of that archive.

This is deliberately not equivalent geometry: overview simplification, tile clipping,
quantization and attribute selection explain the size reduction. Exact selected-area
geometry still comes from the existing API (Phase 7 area-1 example: 152,830 bytes).

## Browser behavior

An isolated headless Chrome production-build smoke used deterministic API responses,
the actual generated PMTiles archive via simulated HTTP Range responses, and a blank
local basemap. At 1440×900 and 390×844 it rendered overview boundaries, station detail
and provenance, and toggled the layer panel without JavaScript errors. Four archive
range requests transferred **72,201 bytes** for the browser viewport. The manifest is
one additional small request. This verifies browser integration, not external hosting.

Before the Phase 8 startup correction, a production load issued **three** API requests:
status, an assumed-radius Hydrology query, then another query after MapLibre loaded.
After waiting for the real viewport, it issued **two**: status and one nearby query.
The cold software-rendered smoke reached canvas plus point-result status in 4.34 s;
there is no claim of a latency improvement from the single-run timing. Development
React StrictMode also replays effects, so development counts are not the production
baseline. This corrects the earlier Phase 7 note's code-derived two-request estimate.

Panning still debounces for 350 ms, cancels stale work and keeps previous points
labelled while updating. Enabling another point source adds one bounded request.
Selecting a point adds one detail request; opening a Water Body retains the existing
list then parallel detail/geometry behavior. Enabling the optional overview fetches
its manifest and visible tiles; it never bulk-loads national GeoJSON in the browser.

## Backend

No SQL, index, route or backend filter changed. The Phase 7 spatial index measurements
still apply. The new scaling path is an offline static derivative, not an alternate
API geometry pipeline. No Redis, materialized view, tile server or MLT was added.

## Bundle and limitations

Default production build, with the optional overview configuration unset:

| Asset | Bytes | Gzip, reported by Vite |
| --- | ---: | ---: |
| Initial application JS | 251,891 | 77.56 kB |
| Lazy MapLibre/PMTiles JS | 1,048,685 | 285.95 kB |
| MapLibre worker | 509,702 | Not reported |
| Application CSS | 8,074 | 2.57 kB |
| MapLibre CSS | 82,962 | 10.72 kB |

PMTiles adds a browser reader to the lazy MapLibre chunk. Configuring the optional
overview also retains its control in the application bundle. Production source maps remain disabled;
the existing large MapLibre chunk warning remains visible. There are no Fabric SDK
dependencies in either the frontend or API image. Fabric tenant execution, external
Range/cache behavior, low-end device rendering and Water Body tiling remain unverified
or deferred, and require their own measurements before deployment.

## Final validation

Validated on Node 24.15.0 after a clean `npm ci`: lint, TypeScript, 55 frontend
tests, production build and npm audit (zero vulnerabilities) passed. Python Ruff
lint/format, mypy (73 source files), 551 non-integration tests and 141 integration
tests against disposable local PostGIS passed. The 10 export tests also passed
directly, including optional GeoParquet round-trip, snapshot/presentation mismatch,
overwrite refusal, and portable tile-builder argument/checksum coverage.

Python package build, Docker build, Compose app-profile configuration and
`git diff --check` passed. Inspection of the measured PMTiles metadata confirmed
one snapshot and no temporary local paths. Tests use local fixtures and mocks;
they do not depend on live publisher services. No cloud deployment or Fabric
tenant execution forms part of these results.
