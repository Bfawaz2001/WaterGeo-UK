# WaterGeo UK

An independent, open-source project working towards a consistent geospatial API
for public UK water data, preserving publisher identifiers, provenance,
attribution, and dataset licensing.

**Status: Phase 0 — engineering foundation.** The application currently provides
health and database readiness endpoints. It does not yet ingest or serve water
datasets. The intended product is data infrastructure and a developer API;
a visual explorer comes later.

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

Edit `.env` and fill in its **three distinct password values**. Generate each with:

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

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | HTTP 200: the application can respond, independent of database health. |
| `GET /ready` | HTTP 200: PostGIS is available and the migration revision matches; otherwise HTTP 503 with a generic response. |

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
actual migrations, readiness, PostGIS point operations, and database permission
denials. They do not substitute SQLite for PostgreSQL.

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
migrations/              Alembic environment and initial database baseline
src/watergeo/
  api/                   Application factory, health and readiness endpoints
  core/                  Validated configuration and JSON application logs
  db/                    Connection pool and database readiness check
tests/                   Configuration and HTTP behaviour tests
  integration/           Opt-in PostGIS and migration tests
Dockerfile               Non-root application image
docker-compose.yml       Local database and optional containerised API
pyproject.toml           Package, dependency, and quality-tool configuration
uv.lock                  Resolved dependencies and distribution hashes
```

## Design and next milestone

See the [Phase 0 architecture](docs/architecture/phase-0.md) and
[foundation decision record](docs/adr/0001-engineering-foundation.md) for rationale,
trade-offs, and known limits. Contribution and vulnerability-reporting guidance
are in [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

The [first source assessment](docs/data-sources/ofwat-company-boundaries.md)
examines Ofwat's publicly distributed water-supply and sewerage boundaries, including
their actual fields and geometry quality. **Next milestone:** resolve its licence
edition/attribution and invalid-geometry policy, then design the first water-supply
ingestion-to-PostGIS-to-API implementation. No source is approved for redistribution
merely by being publicly accessible.
