# ADR 0014: Production deployment architecture

- Status: Accepted for deployment foundation; external provisioning pending
- Date: 2026-09-24

## Context

WaterGeo needs a public read-only API without giving internet-facing processes
migration, ingestion or administrator capability. It also needs reproducible
releases, PostGIS, verified database TLS, retained source evidence, backups and
operational checks. The provider comparison is recorded in the dated
[hosting assessment](../deployment/hosting-assessment-2026-09-24.md).

## Decision

Recommend DigitalOcean App Platform and Managed PostgreSQL for the first hosted
environment. Retain portable contracts so the decision can be revisited before
money is spent.

Use four isolated roles:

1. The public API is the GHCR image selected by digest. HTTPS terminates at the
   managed ingress. The process receives only the read-only database secret and
   trusted-host/TLS configuration. It has no source-fetch endpoint.
2. A one-shot deploy job runs the same image with `alembic upgrade head` using
   only migration credentials. API startup never runs migrations.
3. Ingestion is a separate bounded job with only ingestion credentials and
   outbound access to reviewed public publishers. Initially it uses a locked
   repository checkout because the API image deliberately excludes scripts.
   It must retain immutable raw evidence before scheduling is enabled.
4. Managed PostgreSQL/PostGIS uses a private VPC endpoint and provider CA with
   `verify-full`. Administrator credentials are restricted to initial role and
   extension provisioning and break-glass operations.

Pin source base images by multi-architecture manifest digest. Publish AMD64 and
ARM64 application manifests to GHCR with an immutable `sha-<full commit>` tag.
Release tags and `latest` are conveniences; deployment records must retain the
resolved digest. A main push may publish but never deploys automatically.

Do not trust forwarded headers yet. App Platform owns HTTPS redirects and public
TLS. Configure platform request limits and rate controls at the edge instead of
an in-process counter that diverges across replicas.

## Consequences

The design preserves credential boundaries and makes releases auditable. A
512 MiB API plus entry managed database is estimated at US$20.15/month on the
assessment date before other usage. App Platform runs AMD64 even though GHCR also
publishes ARM64 for portability.

Rollbacks select an earlier application digest only when its code is compatible
with the deployed schema. Alembic downgrades are not assumed safe. Additive schema
changes should be deployed before code that requires them; destructive changes
need a separately reviewed expand/migrate/contract plan.

Public go-live remains blocked on actual provisioning, DNS, secret entry, edge
policy, evidence object storage, backup restore rehearsal and monitoring setup.
