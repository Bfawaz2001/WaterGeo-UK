# WaterGeo UK

An independent, open-source project working towards a consistent geospatial API
for public UK water data, preserving publisher identifiers, provenance,
attribution, and dataset licensing.

**Status: Phase 1 — canonical Ofwat ingestion and public boundary API.** The
reviewed April 2024 water-supply release can be loaded as 1,141 canonical areas
with five recorded geometry transformations. Developers can query metadata,
paginate area summaries, retrieve one-area GeoJSON, and look up areas covering a
longitude/latitude. This is a local development service; a hosted API and visual
explorer come later.

Start with the [end-to-end walkthrough](docs/guides/water-supply-walkthrough.md)
for setup, loading, querying, exporting GeoJSON and diagnosing failures.

## Independence and licensing

WaterGeo UK is a personal, independent open-source project. It is not an official
Ofwat product and is not affiliated with, endorsed by, or maintained by Ofwat,
the Environment Agency, Stream, or any water company. Views and design decisions
are the maintainer's own.

Only appropriately licensed public/open data may be integrated. Internal employer
data, systems, credentials, code, and unpublished material must never be used.
The [MIT licence](LICENSE) covers WaterGeo UK source code; it does **not** relicense
third-party datasets. Each future integration needs its own documented licence
and attribution assessment before implementation.

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

Existing databases from before the ingestion role was introduced need that role
provisioned before migration `0003`; editing `.env` alone does not create it. See
the [existing-volume instructions](#existing-database-volumes).

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | HTTP 200: the application can respond, independent of database health. |
| `GET /ready` | HTTP 200: PostGIS is available and the migration revision matches; otherwise HTTP 503 with a generic response. |
| `GET /v1/water-supply/dataset` | Release, source identity, attribution, licence, counts and caveats. |
| `GET /v1/water-supply/areas` | Paginated area summaries without geometry. |
| `GET /v1/water-supply/areas/at-point?lon=-2&lat=52` | All covering areas, including boundary matches, with pagination. |
| `GET /v1/water-supply/areas/{source_id}` | Area labels, publisher notices and reviewed transformation provenance. |
| `GET /v1/water-supply/areas/{source_id}/geometry` | One GeoJSON Feature in WGS84 longitude/latitude. |

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
See [database operations](docs/architecture/phase-0.md#database-lifecycle).

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

With the database at revision `0003`, run these from the repository root:

```bash
uv run --locked python scripts/fetch_ofwat_water_supply.py
uv run --locked python scripts/validate_ofwat_water_supply.py
uv run --locked python scripts/load_ofwat_water_supply.py
```

Retrieval verifies the exact source ZIP and retains it with a provenance manifest
under ignored `data/raw/ofwat/water-supply/`. Validation reports five invalid
publisher polygons (IDs 1, 4, 6, 28, 30). Its strict raw-geometry eligibility result
is separate from canonical acceptance: [ADR 0004](docs/adr/0004-ofwat-v1_5-canonical-transformation.md)
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
self-intersecting in the assessed runtime. [ADR 0006](docs/adr/0006-water-supply-wgs84-presentation.md)
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
infrastructure and migration `0003`, not dataset availability. See the
[API decision](docs/adr/0005-water-supply-api.md) for contracts and limits.

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
migrations/              Alembic revisions through canonical provenance (0003)
scripts/                 Source retrieval, validation, assessment and canonical loader
src/watergeo/
  api/                   Operational routes, water-supply routes and public models
  core/                  Validated configuration and JSON application logs
  db/                    Connection pool, queries and offline presentation assessment
  ingestion/             Verified Ofwat retrieval, decoding, reviewed transforms and atomic load
tests/                   Configuration and HTTP behaviour tests
  integration/           Opt-in PostGIS and migration tests
Dockerfile               Non-root application image
docker-compose.yml       Local database and optional containerised API
pyproject.toml           Package, dependency, and quality-tool configuration
uv.lock                  Resolved dependencies and distribution hashes
```

## Design and next milestone

See the [Phase 0 architecture](docs/architecture/phase-0.md),
[foundation decision record](docs/adr/0001-engineering-foundation.md),
[water-supply schema decision](docs/adr/0002-water-supply-snapshots.md),
[canonical transformation](docs/adr/0004-ofwat-v1_5-canonical-transformation.md), and
[public API decision](docs/adr/0005-water-supply-api.md) and
[WGS84 presentation review](docs/adr/0006-water-supply-wgs84-presentation.md) for rationale,
trade-offs, and known limits. Contribution and vulnerability-reporting guidance are
in [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

The [first source assessment](docs/data-sources/ofwat-company-boundaries.md)
examines Ofwat's publicly distributed water-supply and sewerage boundaries, including
their actual fields and geometry quality. ADR 0004 and migration `0003` now provide
the reviewed canonical ingestion path; the versioned API exposes its provenance
and analytical boundaries. Historical ADRs describe decisions at their acceptance
dates; consult later ADRs for subsequent source-specific decisions.

**Next milestone:** finish Phase 1 operational and developer-usability review before
starting Environment Agency Phase 2. The local ingestion-to-API walkthrough and
reviewed WGS84 output policy are now implemented. Public hosting still requires
the deployment controls described in SECURITY.md; there is no hosted endpoint yet.
