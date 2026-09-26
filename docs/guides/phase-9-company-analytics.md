# Thames Water discharge analytics

Refresh through the existing supervised, source-locked operation:

```sh
uv run --locked python scripts/refresh_sources.py thames-discharge-status
```

For a two-step evidence review, run `scripts/fetch_thames_discharge.py`, inspect the
new immutable directory, then pass it to `scripts/load_thames_discharge.py`.

The additive routes are:

- `GET /v1/thames-water/discharge-status/dataset`
- `GET /v1/thames-water/discharge-status/sites`
- `GET /v1/thames-water/discharge-status/sites/near`
- `GET /v1/thames-water/discharge-status/sites/{site_id}`

List and near routes accept `alert_status` and `alert_past_48_hours`. Filtering occurs
in PostGIS before the 100-record response bound. List pagination pins a snapshot and
uses `after_id`; nearby results are distance ordered. SDK iterators pin the first
snapshot and fail if a later page changes it. Equivalent CLI commands live under
`watergeo thames-water`.

The explorer's Thames layer is optional. Its status and past-48-hours controls are
server-side filters over the complete selected snapshot, followed by nearest-100
selection. The result count is therefore a bounded viewport count, never a national
total. Selecting a site shows permit/watercourse fields and a short source-native
status timeline. Timestamp text remains offset-free. The layer legend and details
repeat the EDM interpretation warning.

Export one immutable operational edition:

```sh
uv run --locked --extra exports watergeo-export \
  --entity thames-discharge-status \
  --base-url http://127.0.0.1:8000 \
  --output data/exports/thames-discharge/<snapshot> \
  --parquet
```

This creates exact point GeoJSON, GeoParquet and a provenance/checksum manifest.
PMTiles is deliberately rejected: 573 dynamic points are efficiently served by the
bounded API and small snapshot files, while a static tile archive could imply stale
operational state.
