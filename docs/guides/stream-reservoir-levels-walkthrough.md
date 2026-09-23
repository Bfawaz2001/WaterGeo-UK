# Stream reservoir-level developer walkthrough

This slice uses Severn Trent Water's public 2025 raw-water reservoir-level edition on
Stream. It is independent, is not endorsed by Stream or Severn Trent Water, and retains
the publisher's CC BY 4.0 attribution and operational caveats.

## Set up and publish

Complete the README database/password setup, start the disposable/local database, and
apply migration 0009:

```sh
uv sync --locked
docker compose up --wait db
uv run --locked alembic upgrade head
uv run --locked python scripts/refresh_sources.py stream-reservoir-levels
```

The refresh uses only the fixed reviewed ArcGIS item and layer. It fetches item/layer
metadata, object IDs, bounded GeoJSON pages, the ID set again and final item metadata.
It rejects redirects, source changes, incomplete pages and altered schemas. Evidence is
retained under `data/raw/refresh/stream-reservoir-levels/RUN_UUID/BUNDLE_UUID/`.

Retry retained evidence without network access:

```sh
uv run --locked python scripts/refresh_sources.py stream-reservoir-levels \
  --evidence-dir data/raw/refresh/stream-reservoir-levels/RUN_UUID/BUNDLE_UUID
```

Exact evidence retries verify every stored reservoir and reading before returning
`existing`. Different accepted evidence creates another immutable snapshot.

## Query the API

Start the API:

```sh
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
```

In another terminal:

```sh
curl --fail http://127.0.0.1:8000/v1/severn-trent/reservoir-levels/dataset
curl --fail 'http://127.0.0.1:8000/v1/severn-trent/reservoir-levels/reservoirs?limit=10'
curl --fail http://127.0.0.1:8000/v1/severn-trent/reservoir-levels/reservoirs/10014
curl --fail 'http://127.0.0.1:8000/v1/severn-trent/reservoir-levels/reservoirs/near?lon=-1.32&lat=52.32&radius_m=50000&limit=10'
curl --fail http://127.0.0.1:8000/v1/severn-trent/reservoir-levels/reservoirs/10014/readings
curl --fail http://127.0.0.1:8000/v1/sources/status
```

Pin reads with the returned `snapshot_id`. Reservoir lists use `next_after_id`; reading
lists use the aware `next_after` timestamp. URL-encode cursor values when sending them.
Latest readings are latest within the pinned 2025 edition, not current conditions.

## Interpret carefully

Reservoir points are publisher locations, not reservoir footprints. Values and capacity
remain in source `ML`; WaterGeo does not convert, interpolate or compare companies.
The publisher warns that levels must not determine hosepipe-ban/supply measures, that
seasonal levels can be normal, that capacity definitions vary, and that the data does
not replace safety checks.

The ArcGIS layer declares the `DATE` field UTC, but summer values appear at 23:00 UTC
on the preceding day. WaterGeo preserves these exact aware timestamps and does not infer
a local calendar date. No relationship to Ofwat boundaries, EA catchments, Hydrology or
Water Quality records is asserted.

No schedule is supplied for this static edition. Review a new item/year before changing
the accepted source contract. See the
[assessment](../data-sources/stream-company-source-assessment.md) and
[ADR 0013](../adr/0013-severn-trent-reservoir-levels.md).
