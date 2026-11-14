# Environment Agency hydrology developer walkthrough

This guide covers England river level/flow station metadata, latest observations
and separately accepted bounded history. Phase 18B.1 adds API-mode historical
discovery and inspection. Public GitHub Pages serves a static mapped edition without
history; scheduled latest-snapshot refresh remains an opt-in operator workflow.

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
as `snapshot_id` and the cursor as `after_id` for subsequent pages. Station detail accepts `snapshot_id`; without one it
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

## Retrieve bounded historical observations

Historical observations are a separate evidence product from the latest-observation
snapshot. One retrieval covers exactly one reviewed measure identity and an inclusive
timezone-aware window of at most 31 days.

```bash
uv run --locked python scripts/fetch_ea_hydrology_history.py \
  MEASURE_ID \
  --from 2026-09-19T00:00:00Z \
  --to 2026-09-19T20:15:00Z
```

The command writes an ignored evidence bundle beneath
`data/raw/environment-agency/hydrology-history/`. Each source page retains its exact
request URL, response hash, request timing and selected response headers. An
incomplete retrieval has no valid completion manifest and cannot be loaded.

Load the printed evidence directory:

```bash
uv run --locked python scripts/load_ea_hydrology_history.py \
  data/raw/environment-agency/hydrology-history/REPLACE_WITH_DIRECTORY_ID
```

The measure identity must already have appeared in an accepted hydrology metadata
snapshot. The loader is append-only. Exact evidence retries verify the actual stored
observation rows before returning `existing`; changed source evidence creates a new
retrieval instead of modifying the earlier one.

Query one explicit stored retrieval:

```bash
curl --fail \
  "http://127.0.0.1:8000/v1/hydrology/history/RETRIEVAL_ID?limit=100"
```

Use `next_after` as the cursor for the following request. `null` means the final page.
The API deliberately requires a retrieval identity: it does not silently choose
between overlapping retrievals or merge observations from different evidence runs.

Historical numeric zero is a real value. A missing numeric value is accepted only
when the publisher quality is exactly `Missing`; its original omission remains in
`source_fields`. Duplicate timestamps within one retrieval, malformed/non-finite
values, observation times outside the requested window, changed provenance metadata
or unexpected pagination fail closed.

## Phase 18B.1: discover and inspect accepted history

In API mode, select a station using the map, search or nearby results, then open
**Historical observations** beneath the latest-measurement cards. Choose a published
measurement and one stored retrieval edition. Friendly measure labels include units,
declared period and a series number; original identities remain under provenance.
The association uses only measures returned by that station's snapshot-pinned detail.
History retains its own retrieval identity and is never assigned to that snapshot.
Unit and period labels come from the selected metadata snapshot, identified separately
in provenance and CSV; history does not store an independent unit definition.

Discovery uses the new read-only endpoint:

```bash
curl --fail 'http://127.0.0.1:8000/v1/hydrology/history/retrievals?measure_id=MEASURE_ID&limit=50'
```

`measure_id` is an exact publisher notation matching `[A-Za-z0-9_.-]{1,256}`,
not a station GUID, label or publisher URL. Results include retrieval ID, measure,
requested inclusive bounds, start/completion times, record count, raw-content and
normalized hashes, normalization version and OGL v3 licence. Ordering is
`retrieval_completed_at DESC, id DESC` using the existing measure/latest index.
Pass `next_after_id` as `after_id` to read older editions; default limit 50, maximum
100. The cursor must identify a stored retrieval for the same measure. Concurrent
new editions appear on a new discovery, rather than entering older continuation
pages. History retrievals are append-only, so an existing continuation anchor stays
stable. No migration, new grants or history UPDATE/DELETE is required.

An empty exact-measure result is HTTP 200 with `items: []`. Invalid identifiers,
unknown query fields, cursor UUIDs, limits or a cursor from another measure return
422; database/unrepresentable discovery failures return 503. The original
`/v1/hydrology/history/{retrieval_id}` remains unchanged, including 404 for an absent
retrieval, limit 1–1,000 and aware observation timestamp `after` pagination.
The discovery route is registered before the UUID route.

Only operators obtain data: use the existing bounded fetch/load commands above,
or the governed `hydrology-history` refresh operation with an explicitly reviewed
measure and window. The browser never triggers ingestion. Changed evidence creates
another independently selectable edition; no newest-wins merge or stitching occurs.

The browser loads pages of at most 1,000 observations with a 10-page,
10,000-record and 20 MiB cumulative serialized-JSON budget; the common transport
also bounds each response to 10 MiB. It validates identities/provenance on every
page, exact publisher measure references, chronological progression, finite values,
Missing quality and final stored-record count. Cancellation and selection-scoped
components prevent older station/measure/retrieval requests replacing newer results.
Discovery is user-paginated and bounded to 200 editions in one panel. Errors, stale
normalization versions and incomplete pagination withhold chart and download; retry
is explicit. No partial-export mode is offered. Switching windows reuses the loaded
complete series. Switching editions or closing/reopening history reloads deliberately;
there is no unbounded cross-station history cache.

**Available recorded period** shows the whole selected retrieval. 24-hour, 7-day
and 30-day presets end at its requested end, not today, and are disabled if the
requested scope does not cover the preset. An accepted requested scope does not
prove continuous readings: earliest/latest observed times, explicit missing values
and irregular gaps remain visible. Empty windows do not invent values.

The shared chart uses elapsed-time X spacing. Null observations break the line;
when a declared period is supplied, gaps exceeding 1.5 times that period also break
it. This is a visualization rule, not a publisher quality verdict or an invented
count of missing records. All numeric points remain in the SVG path without
aggregation, smoothing or reduction. Larger series avoid thousands of keyboard
stops: hover selects the nearest actual observation and a single reading slider
supports keyboard inspection of every record, including missing ones. A paginated
50-row table provides timestamps and quality without mounting a huge table.
Minimum/maximum summarize reported finite numbers only; no risk/trend inference.

**Download observations CSV** exports every accepted observation in the selected
window, including missing-quality rows. Columns retain retrieval and measure IDs,
observation timestamp, numeric value or `missing` state, unit/period metadata,
quality/completeness, complete source-fields JSON, requested scope, retrieval time,
raw/normalized hashes, normalization version, attribution and metadata snapshot ID.
CSV uses UTF-8 with BOM, CRLF rows and escaped quoted cells. Potential spreadsheet
formulas in text receive a leading apostrophe; finite numeric readings, including
negative numbers and zero, retain their numeric value. Thus text protection can
change the spreadsheet-facing spelling of untrusted text; original source-fields
JSON is retained for interpretation. CSV is not a new evidence bundle or Parquet
export and cannot independently attest publisher bytes from hashes alone.

### API versus static publication

API mode provides the complete workflow when an accepted retrieval exists. Public
static mode shows a clearly labelled history-unavailable section and makes no
history API/publisher requests. Existing immutable Pages products remain intact;
this implementation is not deployed by changing the working tree.

A curated static product needs a separate reviewed change: the v1 evidence package
currently validates exactly ten source directories/replay entries, excludes history,
and the builder/browser have no selected history manifest product. Phase 18B.2
must define explicit approved retrieval selections, retain/replay their raw evidence,
verify exact station/measure metadata compatibility, impose aggregate payload bounds,
write checksummed per-retrieval immutable files and a discovery index, version the
optional manifest capability without breaking old editions, and test missing/altered
files plus static browser/chart/CSV acceptance. No implicit nationwide publishing.
