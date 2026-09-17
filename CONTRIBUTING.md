# Contributing

WaterGeo UK is at the first geospatial schema stage. Small, coherent changes with clear
reasoning are welcome. For a new source or a significant architecture change,
open an issue describing the problem and proposed scope before building it.
Keep discussion respectful and constructive.

## Development

Follow the [README setup](README.md#local-development), create a feature branch,
and install the optional hooks with `uv run --locked pre-commit install`.
Use Python 3.12-compatible syntax, a `src` layout, and explicit types in application
code. Keep dependencies purposeful; update and commit `uv.lock` with dependency
changes. Do not commit environments, credentials, downloaded datasets, or generated builds.

Run pytest, Ruff lint/format checks, and `mypy src` before submitting a pull request.
Run the opt-in integration suite for database or migration changes. Describe the
behaviour changed, why it matters, tests actually run, and any limitations.
Do not claim skipped tests passed. No external data access is needed in unit tests.
Pytest uses short tracebacks to avoid displaying database-driver argument values
in verbose source frames. Do not enable `--showlocals` or share unreviewed failure
logs from tests that use credentials; short tracebacks are not a general redactor.

Warnings fail tests except for the documented Starlette 1.6/AnyIO
`BlockingPortal` deprecation inside the upstream test client. Review that narrow
filter when updating Starlette; application warnings must still fail tests.

## Database changes

Create migrations with `uv run --locked alembic revision -m "describe change"`,
review the SQL, and test upgrade/downgrade against a disposable PostGIS database.
Keep application objects in the `watergeo` schema. Update `SCHEMA_REVISION` when
changing the schema expected by the application. Never run migrations at API startup.
The water-supply schema is defined by explicit migrations; no ORM metadata or
autogeneration is configured yet. See the [schema decision](docs/adr/0002-water-supply-snapshots.md).

Administrator provisioning creates roles, the schema, and PostGIS; Alembic owns
application schema evolution. Database role or extension changes need explicit
provisioning instructions for existing volumes.

## Data sources and employment boundary

Before writing an adapter, complete the [source acceptance requirements](docs/data-sources/README.md).
Use only public documentation, public endpoints, and appropriately licensed data.
Never contribute information obtained through privileged employer access.
Retain original identifiers, attribution, and source-specific meaning. Discuss
unclear licences before downloading data for redistribution.

Small fixtures should be synthetic or demonstrably redistributable and must have
their origin recorded. Source code contributions are under the repository's MIT
licence; source dataset licences remain separate.
