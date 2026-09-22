# Water Quality developer walkthrough

Run from the repository root. Follow README database/password setup, start the database,
then use `uv sync --locked` and `uv run --locked alembic upgrade head` (0008).
The API uses the read-only application role; refresh uses the ingestion role.

## 1. Load sampling-point metadata

Fetch and publish a bounded complete snapshot:

```sh
uv run --locked python scripts/refresh_sources.py water-quality
```

To reuse the reviewed local evidence instead:

```sh
uv run --locked python scripts/refresh_sources.py water-quality \
  --evidence-dir data/raw/environment-agency/water-quality/sampling-points/d362e6ec-19c3-47a7-8e5c-0c9a336dce91
```

Evidence must exist locally; raw bundles are ignored by Git. Exact retries verify stored
content. Keep the snapshot ID from the completion event for reproducible reads.

## 2. Read metadata

Start the API, then read it in another terminal:

```sh
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
```

```sh
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8000/v1/water-quality/dataset
curl --fail 'http://127.0.0.1:8000/v1/water-quality/sampling-points?limit=10'
curl --fail 'http://127.0.0.1:8000/v1/water-quality/sampling-points/MD-GWW20%2F01'
curl --fail 'http://127.0.0.1:8000/v1/water-quality/sampling-points/near?lon=-0.7&lat=52.5&radius_m=10000&limit=10'
curl --fail http://127.0.0.1:8000/v1/sources/status
```

Use the returned `snapshot_id` query parameter on subsequent metadata requests and
URL-encode `next_after_id` as `after_id` for the next list page. Preserve all spaces
and slashes in source notations. Unlocated points remain in lists but not nearby results.
Publisher region/area fields do not identify WaterGeo catchments or water companies.

## 3. Fetch actual observations

This reviewed example requests BOD observations at AN-CORBY for one calendar day:

```sh
uv run --locked python scripts/refresh_sources.py water-quality-observations \
  --sampling-point-id AN-CORBY --determinand 0085 \
  --from 2020-01-23 --to 2020-01-24 --timeout-seconds 300
```

The end date is exclusive; equal dates are invalid. The maximum window is 31 days.
The point must already exist in compatible metadata. Save the completion event's
`snapshot_id`: for this source it is the observation retrieval UUID. Read it with:

```sh
curl --fail 'http://127.0.0.1:8000/v1/water-quality/observations/RETRIEVAL_UUID?limit=100'
```

Replace `RETRIEVAL_UUID`. Use `next_after_id` as a URL-encoded `after_id` to continue.
Responses include scope, metadata snapshot, hashes, retrieval times, determinand and
units. `observed_at_text` preserves publisher time without inventing a timezone.
For `<0.98`, `upper_bound=0.98` and `numeric_value=null`: this is a censored result,
not a measurement equal to the bound. Missing values remain null. No unit conversion
or water-safety classification is performed. Publisher sample relationships remain visible.

## 4. Retry and operate

```sh
uv run --locked python scripts/refresh_sources.py water-quality-observations \
  --evidence-dir data/raw/refresh/water-quality-observations/RUN_UUID/BUNDLE_UUID
```

Replace both UUIDs with the retained evidence path. Do not pass scope arguments with
offline evidence. Validation precedes atomic insertion; exact retry verifies children,
while changed source evidence receives a separate immutable retrieval. Partial or
malformed responses fail closed. Publisher pagination has no atomic-snapshot guarantee.

Metadata retrieval freshness is optionally configured by
`WATERGEO_WATER_QUALITY_RETRIEVAL_MAX_AGE_SECONDS`; unset means unknown. It does not
measure historical result freshness. No Water Quality schedule is automatically enabled.
See [operations](source-operations.md), [source evidence](../data-sources/environment-agency-water-quality-observations.md)
and [ADR 0012](../adr/0012-bounded-water-quality-observations.md).
