# Phase 7 explorer performance baseline

Measured 2026-09-25 on the local Docker PostgreSQL/PostGIS service and Vite 8.3.1
production build. Timings are single local observations for path comparison, not a
production latency promise. The database contained the retained reviewed snapshots:
2,982 Hydrology stations, 66,300 Water Quality sampling points, 14 reservoirs,
1,141 water-supply areas and 4,929 Water Bodies.

## Browser build

| Asset | Bytes | Gzip reported by Vite |
| --- | ---: | ---: |
| Initial application JavaScript | 245,281 | 75.97 kB |
| Initial application CSS | 7,540 | 2.46 kB |
| Lazy MapLibre JavaScript | 1,028,793 | 278.38 kB |
| MapLibre worker | 509,702 | not reported |
| Lazy MapLibre CSS | 82,962 | 10.72 kB |
| HTML | 507 | 0.31 kB |

The largest asset is the 1,028,793-byte MapLibre renderer chunk. Vite emits a
greater-than-500-kB warning for that understood dependency; the warning is retained.
Map code is isolated through dynamic import, while the worker follows MapLibre's
official Vite bundling guidance. Production source maps are disabled. There are
3 top-level runtime and 17 top-level development dependencies.

## Request behavior

Default application state issues exactly two WaterGeo requests: source status and
one debounced Hydrology nearby query. The independently hosted basemap style/tiles
add provider-controlled requests and are excluded from the WaterGeo count. Enabling
each other point layer adds one parallel nearby request. Map movement aborts and
replaces those requests after 350 ms. Water Bodies make one list request only when
opened, then two parallel requests (detail and geometry) on selection. Water-supply
map click makes one lookup and one geometry request only after a match is selected.

## Representative HTTP responses

The local TestClient used a point at `-1.318082, 53.332815` and maximum UI radii.

| Route | Status | Bytes | Local elapsed |
| --- | ---: | ---: | ---: |
| Hydrology nearby, 100 results/100 km | 200 | 38,557 | 69.21 ms |
| Water Quality nearby, 100 results/100 km | 200 | 40,453 | 207.14 ms |
| Reservoir nearby, 14 results/200 km | 200 | 6,670 | 14.05 ms |
| Water-supply geometry, area 1 | 200 | 152,830 | 77.68 ms |
| Water Body geometry, 2 features | 200 | 10,936 | 18.18 ms |
| Source status | 200 | 6,124 | 13.68 ms |

The UI avoids the measured 152,830-byte area geometry until selection and never
downloads all 1,141 area geometries. The initial measured WaterGeo payload is about
44.7 kB before HTTP compression using the status and representative Hydrology page.

## Database plans

`EXPLAIN (ANALYZE, BUFFERS)` used the existing accepted data and exact spatial
predicate shapes. Hydrology used `hydrology_station_geography` (22.13 ms, 850 spatial
candidates); Water Quality used `water_quality_sampling_point_geography` (138.23 ms,
15,508 candidates); reservoirs used `stream_reservoir_geography` (0.09 ms);
water-supply point lookup used `water_supply_area_geom_idx` (11.83 ms); and Water Body
geometry used its composite primary-key index (0.15 ms).

All relevant paths use their intended spatial or identity index and remain bounded
well below the three-second API statement timeout in this dataset. Water Quality is
the heaviest because exact-distance ordering considers 15,508 points inside the
100-km radius before returning 100. A KNN approximation could change exact ordering,
and a multi-column geography index would add extension/schema cost without measured
production history. No backend query or index change is justified at this checkpoint.
Future work should repeat these measurements with representative production traffic
before changing that contract. No Redis, materialized view, bbox route or vector-tile
pipeline was added.
