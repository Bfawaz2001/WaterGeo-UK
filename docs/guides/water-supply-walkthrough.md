# From an empty checkout to a water-supply API

This walkthrough runs a local development service for the reviewed **April 2024
Ofwat v1.5 water-supply snapshot**. It is not a live supplier directory, legal
boundary service, water-quality monitor or hosted API.

## 1. Prepare the checkout

Install Python 3.12+, uv and Docker Desktop. Start Docker Desktop and wait until
its engine is running. In a terminal, enter the repository directory:

```bash
git clone https://github.com/Bfawaz2001/WaterGeo-UK.git
cd WaterGeo-UK
uv sync --locked
docker version
docker compose version
```

If you already have this checkout, use it and skip `git clone`. Docker commands
must work before proceeding; downloading the installer alone does not start the
engine. Repository commands below run from the project root.

For a new checkout without `.env`:

```bash
cp .env.example .env
```

Open `.env` in your editor. Generate **four separate** values by running the next
command four times, then paste each value after the corresponding `=`:

```bash
python3 -c 'import secrets; print(secrets.token_hex(24))'
```

| Setting | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Database administrator bootstrap |
| `WATERGEO_MIGRATION_PASSWORD` | Schema migrations |
| `WATERGEO_DB_PASSWORD` | Read-only API access |
| `WATERGEO_INGESTION_PASSWORD` | Restricted canonical data loading |

Keep existing passwords when reusing an existing database. Changing `.env` does
not change database role passwords. Never commit `.env`. If another database uses
5432, choose an unused `WATERGEO_DB_PORT` in `.env`, such as 5433. Both Compose and
Python tools read it.

## 2. Start and migrate the database

```bash
docker compose up --build --wait db
uv run --locked alembic upgrade head
uv run --locked alembic current
```

Expected schema revision: **0003**. An existing pre-0003 database may need the
ingestion role bootstrapped using the [README instructions](../../README.md#existing-database-volumes).
Do not delete an existing volume to solve a missing-role error.

## 3. Retrieve, inspect and load the source

```bash
uv run --locked python scripts/fetch_ofwat_water_supply.py
uv run --locked python scripts/validate_ofwat_water_supply.py
uv run --locked python scripts/load_ofwat_water_supply.py
```

The fetch verifies the exact archive SHA-256. Raw files and local reports live in
ignored `data/` directories. Validation reports five invalid source geometries:
**1, 4, 6, 28 and 30**. This is expected for this exact publisher archive.
[ADR 0004](../adr/0004-ofwat-v1_5-canonical-transformation.md) permits only their
reviewed canonical transformations; it does not allow generic repairs.

The loader should produce **1,141 canonical areas and five transformation records**.
Run it again to check idempotence:

```bash
uv run --locked python scripts/load_ofwat_water_supply.py
```

Expected result: **verified no-op**. It compares stored content against the
reviewed canonical snapshot. It does not overwrite different stored data.

## 4. Start the API

Keep this command running in one terminal:

```bash
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
```

Open <http://127.0.0.1:8000/docs>. Use a second terminal for the following commands:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8000/v1/water-supply/dataset
```

Metadata should show 1,141 areas, five canonical transformations, source release
`v1_5`, and `licence_version: null`. The source names OGL but does not identify its
edition. `transformation_version` describes canonical ingestion;
`presentation_version` describes WGS84 output separately. `/ready` checks schema
and connectivity, not whether the dataset is loaded.

## 5. Find and retrieve an area

```bash
curl --fail 'http://127.0.0.1:8000/v1/water-supply/areas?limit=2'
curl --fail 'http://127.0.0.1:8000/v1/water-supply/areas?limit=2&after_id=2'
curl --fail 'http://127.0.0.1:8000/v1/water-supply/areas/at-point?lon=-2&lat=52'
curl --fail http://127.0.0.1:8000/v1/water-supply/areas/4
mkdir -p data/exports
curl --fail http://127.0.0.1:8000/v1/water-supply/areas/4/geometry --output data/exports/area-4.geojson
```

Use each page's `next_after_id` for the next page; stop at `null`. The example's
first page has IDs 1 and 2. Point pagination must keep the same longitude and
latitude. Coverage includes boundaries, so more than one area can match. A point
inside a hole does not match that polygon. There is no bbox parameter yet.

GeoJSON coordinates are **longitude, latitude**. Its `presentation` member tells
you whether the area used plain reprojection or the exact reviewed exception.
The four presentation exceptions are **3, 4, 16 and 21**, a different set from
the five source-ingestion transformations. The stored geometry remains BNG
(EPSG:27700) and still drives point queries.

The service was verified to return valid GeoJSON for all 1,141 areas in the
reviewed runtime. The exception's input and output hashes must match exactly;
different transformation libraries/grids can cause a protective 503. Read
[ADR 0006](../adr/0006-water-supply-wgs84-presentation.md) before interpreting or
changing that contract. A GeoJSON provenance hash describes PostGIS's geometry
text, not the entire HTTP response file.

## 6. Reproduce presentation evidence

With the reviewed snapshot loaded:

```bash
uv run --locked python scripts/assess_water_supply_presentation.py
```

This offline tool uses the **read-only API credential**. It scans plain-reprojection
output for all 1,141 areas, then compares fixed candidates for failures. It writes
a new timestamped JSON report under `data/validation/ofwat/water-supply/`. The
baseline remains plain reprojection even when the API presentation policy is
enabled. Expected baseline failures in the reviewed runtime: 3/4/16/21.

The diagnostic has a 60-second **per-statement** timeout, a one-million-vertex
densification budget and a maximum of 20 failing areas to assess. The complete
assessment can take several minutes. It does not alter API timeouts, approve a
policy or modify database rows. Use `--output path/to/new-report.json` for another
destination; an existing file is never overwritten. Reports record library
versions, hashes and measurement limitations.

## Common responses

| Response | What to check |
| --- | --- |
| `/health` 200, `/ready` 503 | Database engine, credentials and migration revision |
| `/ready` 200, `/dataset` 503 | Load the exact reviewed snapshot; inspect sanitized application logs |
| One geometry 503 | Representation invalid or reviewed output hash mismatch; preserve the failure and collect assessment evidence |
| 404 | Source ID does not exist in the loaded snapshot |
| 422 | Invalid coordinates/ID/pagination, missing inputs or unsupported parameters |
| 413 | Serialized geometry exceeds 8 MiB |
| Point lookup returns no items | No matching area in this snapshot, or coordinates outside its processing extent |

Do not replace hashes, bypass validation, or run arbitrary repair SQL to suppress
a 503. Source appointment-map, premises, coastline and historical-data caveats
remain relevant even when a request succeeds.

## Tests and shutdown

Run unit checks using the [README commands](../../README.md#checks). Migration
integration tests require a **separate disposable database**; never point them at
your loaded development database.

Stop the host API with Ctrl-C. To stop Compose while retaining data:

```bash
docker compose down
```

Avoid `down --volumes` for the development database: it deletes its named volume.
Public hosting, live Environment Agency data, an SDK and the map interface remain
later work. This walkthrough completes the first local source-to-API path.
