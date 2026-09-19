# Environment Agency hydrology developer walkthrough

Phase 1 is complete. This first Phase 2 slice covers England river level/flow
stations, measure definitions and latest available observations. It has no scheduled
refresh, historical API or public hosting.

## Prepare and retrieve

Follow [local setup](../../README.md#local-development), including four distinct
passwords in your ignored .env and a running Docker database. From the repository root:

```bash
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python scripts/fetch_ea_hydrology.py
```

The fetcher uses fixed official URLs, writes ignored raw responses and prints the
new evidence directory and validated counts. Retain that directory for audit/retry.
Compare spatial completeness and source counts with the
[dated verification](../data-sources/environment-agency-hydrology-verification.json).
Counts may change; investigate substantial changes, never edit data to match them.
A failed pull has no complete manifest and cannot be loaded. Do not commit raw files.

## Load and inspect

Replace the example path with the directory printed by retrieval:

```bash
uv run --locked python scripts/load_ea_hydrology.py data/raw/environment-agency/hydrology/REPLACE_WITH_DIRECTORY_ID
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
```

The loader uses watergeo_ingest and commits a complete snapshot atomically.
Retrying the same evidence returns a verified no-op. New retrieval content creates
another snapshot; prior rows are retained. A material spatial-completeness drop
returns a validation error for review. The first load has no prior stored comparison,
so review its reported counts against source evidence before relying on it.

```bash
curl --fail http://127.0.0.1:8000/v1/hydrology/dataset
curl --fail 'http://127.0.0.1:8000/v1/hydrology/stations?limit=10'
curl --fail 'http://127.0.0.1:8000/v1/hydrology/stations/near?lon=-1&lat=52&radius_m=10000&limit=10'
curl --fail http://127.0.0.1:8000/v1/hydrology/stations/32f5b1ea-29f7-4d6c-b473-a9e5da0e59d1_U30028
```

The last request is Banks Road. Its missing location remains null; its measures and
observations remain available. Nearby search excludes unlocated stations and
reports the coverage limitation. Distances use WGS84 geography in metres, with
station ID breaking equal-distance ties. Radius is bounded to 100 km and limit to 100.

List pages contain a dataset snapshot ID and next_after_id. Send that snapshot ID
as `snapshot_id` and the cursor as `after_id` for subsequent pages. Station detail
uses the newest compatible snapshot. Source links and original semantic fields
appear with each measure; quality flags are in the latest observation's source_fields.

## Interpret freshness and failures

Retrieval time says when WaterGeo downloaded the response. `observed_at` says when
the reading was measured. An old reading stays old; a recently downloaded snapshot
is not proof of fresh observations. A missing-valued reading is distinct from no
reading and from numeric zero. Preserve the OGL v3 attribution when redistributing.

- 503: database unavailable, no loaded compatible snapshot or invalid stored output.
- 404: station identity absent from the selected current snapshot.
- 422: invalid/unknown input, excessive radius or limit.
- Retrieval/load validation failure: inspect retained public evidence and source
  assessment. Never bypass validation by dropping records or making up coordinates.

CI uses synthetic source responses and disposable PostGIS only. The real source
verification is a separate manual operation; do not add live downloads to CI.
