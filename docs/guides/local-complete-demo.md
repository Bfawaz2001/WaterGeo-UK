# Run the complete local demo

This workflow loads accepted source snapshots into the existing local database. It
never changes or deletes the Docker volume, bypasses source validation, or makes the
browser contact a publisher.

## Prepare and inspect

Start PostgreSQL and migrate it, then inspect what is already available:

```bash
docker compose up --build --wait db
uv run --locked alembic upgrade head
uv run --locked watergeo-demo-bootstrap --status
uv run --locked watergeo-demo-bootstrap --dry-run
```

The command checks database readiness at revision `0011`, reads compatible accepted
snapshots and marks each source as available, stale or not loaded. A dry run says
whether each missing source can use retained local evidence or needs a publisher
retrieval. Static/versioned and dynamic/latest-available sources are labelled
separately.

## Load missing sources

```bash
uv run --locked watergeo-demo-bootstrap
```

Already compatible snapshots are preserved. For a missing source, the bootstrap
prefers the newest retained accepted bundle and sends it through the existing
source reader, validation, advisory lock and atomic loader. If no bundle exists, it
announces the fixed publisher retrieval before starting it. Catchments can take much
longer than the other sources and have a two-hour bound.

Use `--offline` to prohibit publisher traffic. Use repeatable `--source`, for example
`--source ofwat --source hydrology`, to request a subset. Independent failures do not
prevent safe work on later sources, but any requested missing or failed source makes
the command exit nonzero. Evidence and snapshot identities remain unchanged on
verified no-op retries.

The April 2024 Ofwat release, Cycle 3 catchments and Severn Trent 2025 edition are
dated static/versioned data. They are not live supplier, catchment or reservoir
conditions. Hydrology, Water Quality metadata and Thames status represent the latest
accepted WaterGeo retrieval, subject to their explicit freshness caveats.

## Start and verify

Start the API and Vite explorer as described in the README, then run:

```bash
uv run --locked watergeo-demo-smoke http://127.0.0.1:8000 --complete
```

The smoke command calls only WaterGeo. It checks `/health`, `/ready`, source status,
unified search and one bounded query for every loaded demo source. It reports `PASS`,
`NOT LOADED`, `SKIP` or `FAIL`. For the production-shaped edge rehearsal, use
`http://127.0.0.1:8080 --complete --explorer` so the built explorer HTML is checked too.

## Phase 12 local diagnosis

On 27 September 2026 the retained development volume was healthy at Alembic `0011`.
It contained one compatible Water Quality snapshot with 66,300 sampling points. The
water-supply, Hydrology, Catchment, Severn Trent and Thames snapshot tables contained
zero rows. Their unavailable state was therefore caused by datasets never being
loaded into that volume. No Phase 11 application or normalization regression was
found. Retained local evidence exists for replay; the bootstrap does not delete the
accepted Water Quality state.
