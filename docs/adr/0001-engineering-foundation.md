# ADR 0001: A small API and PostGIS foundation

- Status: Accepted for Phase 0
- Date: 2026-09-15

## Context

WaterGeo UK needs reproducible Python engineering and a geospatial database, but
no source dataset has yet been investigated or approved. The maintainer develops
on Apple Silicon. A dataset model designed without real source evidence risks
discarding provenance or combining concepts that deserve separate tables.

## Decision

Use Python 3.12, uv with a committed lockfile, a `src` package, FastAPI, Pydantic
settings, SQLAlchemy 2/Psycopg 3, and Alembic. Begin with synchronous database
access and operational endpoints only. Provision PostgreSQL 17/PostGIS locally;
give the API read-only grants and use a separate migration role. Administrators
own extension/role provisioning; migrations own later application schema changes.

Build the database image from the official multi-architecture `postgres:17-bookworm`
image and install `postgresql-17-postgis-3` from its configured PostgreSQL package
repository. At review time the PostGIS project documented its published images as
AMD64-only. This build supports the intended native ARM64 workflow without an
architecture override. PostgreSQL 17 is an intentional supported baseline, not a
claim to use the latest major release.

Use separate liveness and readiness checks. Readiness requires the specific schema
revision the application understands. Keep migrations out of API startup to avoid
giving HTTP workers schema-changing credentials.

## Consequences

- The first milestone validates packaging, configuration, HTTP behaviour, and the
  database operational boundary without making up domain entities.
- Separate credentials and a small PostgreSQL Dockerfile add setup work, justified
  by least privilege and Apple Silicon development.
- Exact schema readiness is easy to reason about now; rolling multi-version
  deployments will need an explicit compatibility policy later.
- Building from OS packages trades full image reproducibility for a smaller
  maintenance burden. Before deployment, pin image digests and define image and
  extension upgrade processes, including vulnerability scanning of OS packages.
- Heavy geospatial/file-processing libraries are deferred until data handling
  requires them. Provider abstractions follow concrete integrations.

## References reviewed

- [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [PostGIS image architecture and versions](https://github.com/postgis/docker-postgis)
- [PostgreSQL Debian repository architecture support](https://www.postgresql.org/download/linux/debian/)
- [SQLAlchemy Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Starlette test client changes](https://github.com/Kludex/starlette/blob/main/docs/release-notes.md)
