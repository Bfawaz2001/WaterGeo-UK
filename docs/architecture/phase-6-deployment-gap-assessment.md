# Phase 6 deployment gap assessment

Assessment date: 2026-09-24. Baseline: `fd28eedc43fc741f136c2819fefd89fc7c979617`.

## Existing strengths

- The API, migrator, ingestion and administrator database identities are separate.
- The API pool, connection, lock and statement waits are bounded; all public data
  routes have typed limits and large geometry output is capped at 8 MiB.
- The container runs as UID/GID 10001. Local Compose uses a read-only filesystem,
  drops capabilities, prevents privilege gain, and keeps ports on loopback.
- `/health` is process liveness. `/ready` verifies PostGIS and exact Alembic head.
- Database URLs are structured, secrets are hidden, and remote TLS supports only
  `verify-full`. The Docker context allowlist excludes `.env` and raw evidence.
- Scheduled Hydrology refresh is bounded and has a distinct ingestion identity.

## Gaps found and disposition

| Gap | Phase 6 disposition |
| --- | --- |
| Base images were mutable tags | Pin Python, uv and PostgreSQL manifest-list digests while retaining readable tags. |
| No published application image | Add a guarded multi-architecture GHCR workflow with immutable commit tags, release aliases, SBOM and provenance. It does not deploy. |
| Any `Host` was accepted | Require explicit trusted hosts in production and enable Starlette trusted-host validation only there. |
| Production could start without verified database TLS | Production settings now require `verify-full` and a CA path. Development behavior remains unchanged. |
| Reverse-proxy trust was undefined | Continue disabling proxy headers. Decide the exact platform ingress address range before enabling them; current routes do not depend on client IP or externally generated absolute URLs. |
| No remote deployment check | Add a bounded explicit-URL smoke command covering liveness, readiness, OpenAPI, optional data, invalid requests and leakage markers. |
| Image rollout/migration order was undocumented | Define build-by-digest, one-shot migration, revision check, API rollout, readiness and smoke gates. API replicas never migrate. |
| Raw evidence is only in ignored local directories | Require encrypted versioned object storage with hashes and retention before production refresh scheduling. This remains a go-live blocker. |
| Managed database backups had no restore contract | Define backup targets, restore rehearsal and verification; provider backups are only one layer. |
| No production edge abuse policy | Retain application bounds and require edge request-rate, size, connection and timeout limits. Avoid a misleading per-process limiter. |
| No minimum production monitoring contract | Define availability, latency/status, restarts, database, source freshness and refresh outcome signals. |
| API image deliberately excludes operator scripts | Preserve that boundary. Use a separate source-based, least-privilege job initially; design a dedicated operator image only with durable evidence transfer. |

## Remaining external decisions

The public hostname, region, traffic estimate, edge limits, retention periods,
alert destination, recovery objectives and exact trusted ingress network need an
operator decision. Production ingestion cannot be enabled until evidence upload
is durable and failure-tested. These are explicit go-live blockers rather than
defaults hidden in application code.
