# Local platform and API reference

Detailed setup, endpoint inventory, existing-volume procedures and checks moved from the README. The public Pages site does not host this API.

## Local development

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and a running Docker engine with Docker Compose v2. Development and CI use Python
3.12. The container build targets native ARM64 and AMD64, including Apple Silicon;
both architectures have CI integration jobs.

```bash
uv sync --locked
cp .env.example .env
```

Edit `.env` and fill in **four distinct password values**: `POSTGRES_PASSWORD`,
`WATERGEO_MIGRATION_PASSWORD`, `WATERGEO_DB_PASSWORD`, and
`WATERGEO_INGESTION_PASSWORD`. Generate each with:

```bash
python3 -c 'import secrets; print(secrets.token_hex(24))'
```

Passwords must be at least 16 characters. Hex values avoid dotenv quoting issues.
Do not commit `.env`. There are no working default passwords.

```bash
docker compose up --build --wait db
uv run --locked alembic upgrade head
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
```

Open <http://127.0.0.1:8000/docs> for OpenAPI documentation.

For typed Python client and read-only CLI examples, see the
[developer quickstart](../guides/developer-quickstart.md). WaterGeo has no hosted
FastAPI endpoint; configure the client or CLI with a local or self-hosted server URL.

Existing databases from before the ingestion role was introduced need that role
provisioned before migration `0003`; editing `.env` alone does not create it. See
the [existing-volume instructions](#existing-database-volumes).

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | HTTP 200: the application can respond, independent of database health. |
| `GET /ready` | HTTP 200: PostGIS is available and the migration revision matches; otherwise HTTP 503 with a generic response. |
| `GET /v1/water-supply/dataset` | Release, source identity, attribution, licence, counts and caveats. |
| `GET /v1/sources/status` | Accepted source availability, retrieval/observation ages and explicit freshness policy. |
| `GET /v1/search?q=river&limit=24` | Bounded current-snapshot prefix/identity search across nine explorer entity types. |
| `GET /v1/rainfall/dataset` | Latest accepted rainfall snapshot, licence, provenance and precision caveat. |
| `GET /v1/rainfall/stations[/near]` | Paginated or bounded nearby EA rainfall gauges and latest publisher-period accumulation. |
| `GET /v1/flood-monitoring/dataset` | Latest accepted operational flood snapshot and emergency-service caveat. |
| `GET /v1/flood-monitoring/areas` | Official flood-area geometry with exact publisher warning severity where present. |
| `GET /v1/bathing-waters[/near]` | Publisher bathing-water identity, classification and sample/advice relations. |
| `GET /v1/company-performance/companies/{company_id}` | Generic publication-period Ofwat measures with explicit missing/N/A states. |
| `GET /v1/severn-trent/reservoir-levels/dataset` | Pinned 2025 company reservoir-level edition and provenance. |
| `GET /v1/severn-trent/reservoir-levels/reservoirs` | Keyset-paginated reservoir locations and latest edition reading. |
| `GET /v1/severn-trent/reservoir-levels/reservoirs/near` | Bounded WGS84 distance search over publisher points. |
| `GET /v1/severn-trent/reservoir-levels/reservoirs/{reservoir_id}` | Reservoir detail with exact publisher identity. |
| `GET /v1/severn-trent/reservoir-levels/reservoirs/{reservoir_id}/readings` | Pinned timestamp-keyset readings without unit conversion or risk inference. |
| `GET /v1/water-quality/dataset` | Compatible sampling-point snapshot, provenance and spatial completeness. |
| `GET /v1/water-quality/sampling-points` | Snapshot-pinned keyset listing of sampling points. |
| `GET /v1/water-quality/sampling-points/near` | Bounded WGS84 geography search, ordered by distance and identity. |
| `GET /v1/water-quality/sampling-points/{sampling_point_id}` | Sampling-point detail; opaque spaces and slash IDs are preserved. |
| `GET /v1/water-quality/observations/{retrieval_id}` | Pinned bounded observations with determinand, unit, result qualifiers and sample provenance. |
| `GET /v1/water-supply/areas` | Paginated area summaries without geometry. |
| `GET /v1/water-supply/areas/at-point?lon=-2&lat=52` | All covering areas, including boundary matches, with pagination. |
| `GET /v1/water-supply/areas/{source_id}` | Area labels, publisher notices and reviewed transformation provenance. |
| `GET /v1/water-supply/areas/{source_id}/geometry` | One GeoJSON Feature in WGS84 longitude/latitude. |
| `GET /v1/water-supply/companies` | Complete derived publisher-acronym index for one accepted boundary snapshot. |
| `GET /v1/water-supply/companies/{acronym}/areas` | Snapshot-pinned, keyset-paginated complete company-area inventory. |
| `GET /v1/water-supply/companies/{acronym}/geometry` | Bounded exact FeatureCollection for the verified inventory; no dissolve. |
| `GET /v1/hydrology/dataset` | Current reviewed Environment Agency hydrology snapshot metadata and coverage. |
| `GET /v1/hydrology/stations` | Paginated river level/flow station summaries. |
| `GET /v1/hydrology/stations/near` | Nearby located stations using WGS84 geography distance. |
| `GET /v1/hydrology/stations/{station_id}` | Station, measures and latest available observations. |
| `GET /v1/hydrology/history/{retrieval_id}` | One explicit bounded historical retrieval with cursor pagination. |
| `GET /v1/catchments/dataset` | Current reviewed Catchment Data Explorer Cycle 3 snapshot metadata and hierarchy counts. |
| `GET /v1/catchments/river-basin-districts` | Snapshot-pinned paginated River Basin District summaries. |
| `GET /v1/catchments/river-basin-districts/{entity_id}` | One River Basin District with publisher provenance. |
| `GET /v1/catchments/management-catchments` | Snapshot-pinned paginated Management Catchments. |
| `GET /v1/catchments/management-catchments/{entity_id}` | One Management Catchment and its River Basin District identity. |
| `GET /v1/catchments/operational-catchments` | Snapshot-pinned paginated Operational Catchments. |
| `GET /v1/catchments/operational-catchments/{entity_id}` | One Operational Catchment with its publisher hierarchy. |
| `GET /v1/catchments/water-bodies` | Snapshot-pinned paginated Water Body summaries. |
| `GET /v1/catchments/water-bodies/{entity_id}` | One Water Body with full publisher hierarchy identities. |
| `GET /v1/catchments/water-bodies/{entity_id}/geometry` | Publisher Water Body geometry features as WGS84 GeoJSON. |

See the [Water Quality walkthrough](../guides/water-quality-walkthrough.md) for
metadata and bounded observation refresh, pinned reads and evidence retries.

The database and API ports bind only to loopback. If port 5432 is occupied, change
`WATERGEO_DB_PORT` in `.env`; Compose and host-based Python tools use the same value.
The Compose database name is `watergeo` and its role names are fixed.

### Run the application in containers

With passwords configured in `.env`:

```bash
docker compose --profile app up --build --wait
```

This starts PostgreSQL/PostGIS, runs Alembic as a one-shot migration service, then
starts the API as a non-root user with a read-only filesystem. Only the migration
service receives migration credentials; the API receives its read-only credential.
The default Compose profile starts just the database for host-based development.

```bash
docker compose --profile app down
```

The named database volume survives `down`. Initialisation SQL runs only on an
empty volume: changing passwords in `.env` does not rotate existing database roles.
See [database operations](../architecture/phase-0.md#database-lifecycle).

### Existing database volumes

Fresh volumes receive all roles from `docker/postgres/init.sql`. For a pre-0003
volume, first set `WATERGEO_INGESTION_PASSWORD` in `.env` and recreate the database
container to refresh its environment (the existing volume is retained):

```bash
docker compose up --wait --force-recreate db
docker compose exec -T db psql -X -U postgres -d watergeo -v ON_ERROR_STOP=1 <<'SQL'
\getenv ingestion_password WATERGEO_INGESTION_PASSWORD
CREATE ROLE watergeo_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    PASSWORD :'ingestion_password';
GRANT CONNECT ON DATABASE watergeo TO watergeo_ingest;
GRANT USAGE ON SCHEMA watergeo TO watergeo_ingest;
SQL
uv run --locked alembic upgrade head
```

Run this bootstrap only if the role is missing. Migration `0003` grants SELECT and
INSERT on the three ingestion tables; the ingestion role has no UPDATE, DELETE,
schema CREATE, or blanket future-table write grants. The API continues to use the
separate read-only `watergeo_app` role.

## Load and query the reviewed dataset

With the database at migration head (`0012`), run these from the repository root:

```bash
uv run --locked python scripts/fetch_ofwat_water_supply.py
uv run --locked python scripts/validate_ofwat_water_supply.py
uv run --locked python scripts/load_ofwat_water_supply.py
```

Retrieval verifies the exact source ZIP and retains it with a provenance manifest
under ignored `data/raw/ofwat/water-supply/`. Validation reports five invalid
publisher polygons (IDs 1, 4, 6, 28, 30). Its strict raw-geometry eligibility result
is separate from canonical acceptance: [ADR 0004](../adr/0004-ofwat-v1_5-canonical-transformation.md)
approves those five transformations for this exact archive and pinned runtime only.
Canonical loading produces **1,141 areas and five transformation records**, atomically.
Repeating the load verifies stored content and returns a **verified no-op**.

The raw ZIP remains authoritative source evidence. Canonical geometry is an
explicit WaterGeo transformation for analysis; it is not the definitive legal
record. There is no generic automatic repair policy. The source declares
`Open Government Licence`, with **`licence_version = null`** because the edition
is unidentified. The API preserves this uncertainty and exposes the generic
official licence URL, attribution and publisher notices.

Once the API is running:

```bash
curl --fail http://127.0.0.1:8000/v1/water-supply/dataset
curl --fail 'http://127.0.0.1:8000/v1/water-supply/areas?limit=10'
curl --fail 'http://127.0.0.1:8000/v1/water-supply/areas/at-point?lon=-2&lat=52'
curl --fail http://127.0.0.1:8000/v1/water-supply/areas/1
curl --fail http://127.0.0.1:8000/v1/water-supply/areas/1/geometry
curl --fail http://127.0.0.1:8000/v1/water-supply/companies
curl --fail 'http://127.0.0.1:8000/v1/water-supply/companies/ANH/areas?limit=100'
```

Use `next_after_id` as the next request's `after_id`; `null` means the final page.
The maximum page size is 100. Point pagination must retain the same coordinates.
Point queries use PostGIS `ST_Covers`: shared boundaries, overlaps and inset areas
can return multiple results, and points inside holes do not match that area.
This dated snapshot does not establish a property's current supplier. Valid
coordinates outside the conservative GB processing extent (-9..3 longitude,
49..61 latitude) return an empty page.

GeoJSON uses `application/geo+json`, longitude/latitude order, and query-time
reprojection from the stored EPSG:27700 geometry. Output rings follow the right-hand
rule. No simplification is applied; geometry above 8 MiB returns 413, and an invalid
serialized representation or reviewed output hash mismatch returns 503. Transform
accuracy depends on installed PROJ grids and is not a legal or centimetre-accuracy
guarantee. Bbox filtering is
not implemented; unknown parameters, including `bbox`, return 422.

**Reviewed WGS84 presentation:** plain reprojection makes areas **3, 4, 16 and 21**
self-intersecting in the assessed runtime. [ADR 0006](../adr/0006-water-supply-wgs84-presentation.md)
defines a presentation-only structure repair for those exact source IDs and
canonical geometry hashes. Each repaired output must match its reviewed GeoJSON
hash and pass the final validity check; all other areas use plain reprojection.
All **1,141 HTTP GeoJSON outputs** were verified valid in the reviewed environment,
with canonical rows unchanged. Different library/grid outputs fail closed with
503 and require another review. Dataset `presentation_version` and each Feature's
`presentation` member keep output provenance separate from canonical ingestion.

To reproduce the baseline and candidate evidence without changing database data:

```bash
uv run --locked python scripts/assess_water_supply_presentation.py
```

The offline diagnostic writes a new report under ignored `data/validation/` and
uses a bounded 60-second statement timeout; the API retains its three-second
timeout. It never approves transformations or modifies the API policy.

Data routes return 503 until the reviewed snapshot is loaded or if the database
is unavailable; unknown area IDs return 404 once it is loaded. `/ready` checks
infrastructure and migration head (`0012`), not dataset availability. See the
[API decision](../adr/0005-water-supply-api.md) for contracts and limits.

## Query the Catchment Data Explorer hierarchy

After loading a reviewed Cycle 3 snapshot with `scripts/load_ea_catchments.py`, the public API exposes publisher hierarchy entities without inventing a Hydrology station-to-catchment relationship.

Example requests:

    curl --fail http://127.0.0.1:8000/v1/catchments/dataset
    curl --fail 'http://127.0.0.1:8000/v1/catchments/river-basin-districts?limit=10'
    curl --fail http://127.0.0.1:8000/v1/catchments/river-basin-districts/4
    curl --fail http://127.0.0.1:8000/v1/catchments/management-catchments/3101
    curl --fail http://127.0.0.1:8000/v1/catchments/operational-catchments/3471
    curl --fail 'http://127.0.0.1:8000/v1/catchments/water-bodies?limit=10'
    curl --fail http://127.0.0.1:8000/v1/catchments/water-bodies/GB104028047290
    curl --fail http://127.0.0.1:8000/v1/catchments/water-bodies/GB104028047290/geometry

List endpoints use keyset pagination. Pass both `snapshot_id` and `next_after_id` from the previous response to remain pinned to the same accepted snapshot. Page size is limited to 100, and malformed identifiers or unexpected query parameters return 422.

Water Body geometry responses use `application/geo+json` and preserve separate publisher features such as `Catchment` and `RiverLine`; they are not dissolved into a WaterGeo-created parent polygon. Geometry responses above 8 MiB return 413. Missing entities return 404 only after a compatible snapshot is available; source/database contract failures return a generic 503.

## Checks

The default tests need no database or `.env`; integration tests are explicitly skipped.

```bash
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv build
uv run --locked pre-commit install
```

The pre-commit hooks use tools from `uv.lock`. CI repeats the checks independently.

Integration tests temporarily downgrade and re-upgrade the schema. Run them only
against a disposable database. To use a separate local Compose volume and port:

```bash
WATERGEO_DB_PORT=55432 docker compose -p watergeo-test up --build --wait db
WATERGEO_DB_PORT=55432 WATERGEO_TEST_DATABASE=1 uv run --locked pytest -m integration
WATERGEO_DB_PORT=55432 docker compose -p watergeo-test down --volumes
```

The last command deletes **that test project's** database volume. The tests verify
actual migrations, readiness, geometry acceptance/rejection, snapshot provenance,
transaction rollback, and database permission denials. All geometry fixtures are
synthetic. They do not substitute SQLite for PostgreSQL.

For the locked dependency audit (requires internet access):

```bash
uv export --locked --all-groups --no-emit-project --format requirements-txt --output-file /tmp/watergeo-requirements.txt
uv run --locked pip-audit --strict --require-hashes -r /tmp/watergeo-requirements.txt
```

## Repository map

```text
.github/                 CI, security scans, dependency updates
docker/postgres/         Native PostgreSQL/PostGIS build and role provisioning
docs/architecture/       Current design and operational boundaries
docs/adr/                Significant architectural decisions
docs/data-sources/       Source acceptance and provenance requirements
migrations/              Alembic revisions through national products (0012)
scripts/                 Source retrieval, validation, assessment and canonical loader
src/watergeo/
  api/                   Operational, water-supply, hydrology and catchment public routes
  core/                  Validated configuration and JSON application logs
  db/                    Connection pool, queries and offline presentation assessment
  ingestion/             Verified public-source retrieval, normalization and atomic load
tests/                   Configuration and HTTP behaviour tests
  integration/           Opt-in PostGIS and migration tests
Dockerfile               Non-root application image
docker-compose.yml       Local database and optional containerised API
pyproject.toml           Package, dependency, and quality-tool configuration
uv.lock                  Resolved dependencies and distribution hashes
```
