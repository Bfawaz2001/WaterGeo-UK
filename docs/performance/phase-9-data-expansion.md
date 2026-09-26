# Phase 9 measured results

Measured 2026-09-26 on the local Apple Silicon development workstation against
disposable PostGIS. Results describe one retrieval, not production latency or a
publisher service-level objective.

The reviewed response contained 573 sites across approximately
`[-1.96509, 51.07618, 0.30665, 52.16883]` in WGS84 after PostGIS transformation:
548 `Not discharging`, 24 `Offline`, one `Discharging`, and two with the publisher's
past-48-hours flag. The raw response was 272,798 bytes.

| Local API request | Median of 20 warmed calls | Largest | Response bytes |
| --- | ---: | ---: | ---: |
| Dataset metadata | 2.94 ms | 5.11 ms | 1,207 |
| 50 km nearby, maximum 100 | 7.81 ms | 27.61 ms | 51,528 |
| 200 km, `Discharging` only | 5.10 ms | 5.41 ms | 1,719 |

`EXPLAIN (ANALYZE, BUFFERS)` for a 10 km query used
`thames_discharge_site_geography`, returning 80 rows in 2.42 ms with 84 shared-buffer
hits. This evidence justifies the geography GiST index. No status index was added:
573 snapshot rows do not justify another write/storage cost. Existing primary-key
ordering supports snapshot-pinned pagination.

The SDK/API export of all 573 sites completed in 0.27 seconds. GeoJSON was 335,635
bytes and Zstandard GeoParquet was 46,614 bytes. GeoParquet retains typed status,
boolean, source-coordinate and stable identity columns plus WKB point geometry.
Dynamic data is not converted to PMTiles.

Explorer calls remain debounced and abort stale work. Each enabled dynamic layer
adds one bounded request after map readiness. Thames filters replace that request;
they do not fetch a full client-side collection. Rendering remains capped at 100
Thames points, so clustering was not justified by this measurement.
