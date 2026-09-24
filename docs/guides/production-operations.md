# Production deployment and operations

This runbook implements [ADR 0014](../adr/0014-production-deployment-architecture.md).
It describes the reviewed deployment contract; it does not indicate that a hosted
service exists.

## Components and identities

| Component | Reachability | Database identity | Purpose |
| --- | --- | --- | --- |
| HTTPS ingress and API | Public HTTPS; API container private | `watergeo_app` | Read-only HTTP service |
| Migration job | One-shot, no public route | `watergeo_migrator` | `alembic upgrade head` |
| Ingestion job | One-shot, no public route; reviewed outbound HTTPS | `watergeo_ingest` | Fetch, validate and atomically publish source data |
| PostgreSQL/PostGIS | Private VPC/trusted sources only | Separate service administrator | Durable database, role provisioning and break-glass operations |

Never place administrator, migration or ingestion credentials in the API service.
Do not make each API replica run Alembic. The API image contains migration files
but deliberately excludes ingestion scripts and raw data.

## Production configuration and secrets

Set these non-secret API values:

```text
WATERGEO_SERVICE_ENVIRONMENT=production
WATERGEO_TRUSTED_HOSTS=["api.example.org"]
WATERGEO_DB_HOST=<private database hostname matching its certificate>
WATERGEO_DB_PORT=25060
WATERGEO_DB_NAME=watergeo
WATERGEO_DB_USER=watergeo_app
WATERGEO_DB_SSLMODE=verify-full
WATERGEO_DB_SSLROOTCERT=/run/secrets/database-ca.pem
WATERGEO_LOG_LEVEL=INFO
```

The API secret inventory is only `WATERGEO_DB_PASSWORD` and the mounted/read-only
database CA certificate. Migration gets `WATERGEO_MIGRATION_PASSWORD`, its own
username and the same connection/TLS metadata. Ingestion gets
`WATERGEO_INGESTION_PASSWORD`, its own username and TLS metadata. Initial database
provisioning alone gets the provider administrator credential plus three generated
role passwords. The GHCR workflow uses GitHub's scoped `GITHUB_TOKEN`; it has no
cloud or database secret.

Store values in the platform secret manager, mask them from logs, restrict access
by component, and rotate one role at a time. Never save a composed connection URL.
The provider CA may be configuration rather than a secret, but its file must remain
read-only and controlled. Production settings refuse to start without an explicit
trusted host, `verify-full`, and the CA path. `*` is rejected.

TLS terminates at the managed ingress. Keep Uvicorn's proxy-header support disabled
until the exact ingress proxy network is known and tested; never set an unrestricted
proxy allowlist. WaterGeo currently has no client-IP authorization and generates no
external absolute route URLs, so forwarded headers are not required. Configure HTTPS
redirects, certificates and HSTS at the ingress.

## Build and release

`.github/workflows/container-image.yml` builds AMD64 and ARM64 on pull requests
without logging into a registry. In the original repository, main pushes, `v*`
tags, and a manual dispatch on main may publish
`ghcr.io/bfawaz2001/watergeo-uk`. Only the publish job has `packages: write`.
Actions and base images are pinned to immutable commits/digests. Published images
include build provenance and an SBOM.

Deploy the resolved OCI digest, never a mutable alias. `sha-<full commit>` is the
traceable tag. A `v*` release additionally receives that release tag and `latest`.
Publishing does not deploy. Record source commit, GHCR digest, migration revision,
operator, time and smoke result in the release record.

## Database provisioning and rollout

1. Create managed PostgreSQL in the same region/VPC as the app. Enable PostGIS.
   Restrict trusted sources to the API and job components. Download the provider CA.
2. As the provider administrator, adapt and run `docker/postgres/init.sql` once to
   create `watergeo_migrator`, `watergeo_app`, `watergeo_ingest`, schema ownership,
   default read grants and app read-only default. Supply generated passwords through
   protected process environment; do not paste them into shell history or SQL files.
3. Test all three identities over the private hostname with `verify-full`. Confirm
   the API cannot write, ingestion cannot update/delete or create schema, and the
   migrator is not an administrator.
4. Select the reviewed application digest. Run a one-shot migration job from that
   digest with `alembic upgrade head`. Query `watergeo.alembic_version` and require
   `0009`, the revision compiled into this release.
5. Roll the API with only app credentials. Wait for `/health`, then `/ready`.
6. Run the smoke command below. After bootstrap, include a representative data path.
7. Enable public traffic only after backup, edge and monitoring checks pass.

For later releases, apply additive migrations before code that requires them.
Rollback means selecting a previously recorded digest only when it supports the
current schema. Do not automatically run Alembic downgrade; destructive migrations
need a reviewed expand/migrate/contract plan and a tested restore point.

## Edge and runtime controls

Run one Uvicorn process per container and scale replicas at the platform. Keep the
existing five-connection pool with zero overflow in the capacity calculation:
`replicas × 5`, plus migration/ingestion and operator reserve, must remain below the
managed database connection limit. Use graceful platform termination and wait for
the process to close its pool.

At the edge set a conservative request-rate limit, concurrent-connection limit,
maximum request-body size and request timeout. Start with observed traffic and load
tests rather than inventing a permanent number; record the chosen values before
go-live. Keep platform DDoS/basic abuse protection enabled. The application already
bounds page sizes, search radius, geometry size, database pool/waits/statements and
source refresh scope. It accepts read-only GET requests, so an in-memory replica-local
rate limiter would provide misleading protection and is not added.

## Smoke test

Run from a clean locked checkout against an explicit URL:

```sh
uv run --locked python -m watergeo.deployment_smoke https://api.example.org
uv run --locked python -m watergeo.deployment_smoke \
  https://api.example.org --data-path /v1/sources/status
```

The command disables environment proxy inheritance and redirects, uses ten-second
timeouts, bounds every response at 2 MiB, and requires JSON contracts for `/health`,
`/ready`, `/openapi.json`, an optional `/v1/` data path, and a 422 invalid request.
It also rejects common database/stack leakage markers. A data path is mandatory in
the operator's go-live record after bootstrap.

## Monitoring and incident signals

Use platform metrics/logs first. Alert on sustained non-200 `/health`, any failed
`/ready`, elevated 5xx rate/latency, restarts or crash loops, database connection
pressure/storage/CPU, backup failure, and failed migration or refresh jobs. Poll
`/v1/sources/status` against explicitly approved freshness thresholds; do not infer
freshness when policy is unset. Retain refresh exit code/run ID without raw upstream
responses or secrets. Application logs use controlled events and sanitized database
errors; keep access logging at the trusted ingress with bounded retention.

## Go-live checklist

- [ ] Budget, region, owner, public hostname and independent-project wording approved.
- [ ] Immutable image digest and SBOM/provenance recorded.
- [ ] VPC/trusted sources and `verify-full` connection verified for each role.
- [ ] Secret access boundaries and rotation/revocation procedure tested.
- [ ] Migration succeeded and exact revision is `0009`.
- [ ] Production data bootstrap and evidence upload verified.
- [ ] Database backup plus evidence storage retention enabled; restore rehearsed.
- [ ] Edge limits, TLS, HSTS, health checks and alerts configured.
- [ ] Smoke check including representative data passed from outside the platform.
- [ ] Vulnerability reporting, branch protections, secret scanning and response owner set.
- [ ] DNS change and rollback window approved separately.

Provisioning, secret entry, DNS and deployment are external actions and are outside
this repository checkpoint.
