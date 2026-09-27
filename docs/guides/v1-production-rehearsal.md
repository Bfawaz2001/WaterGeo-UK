# V1 production rehearsal

Status: executable local rehearsal; no public infrastructure or Fabric tenant has
been provisioned or validated.

## Same-origin topology

`docker-compose.rehearsal.yml` builds the real `web/dist` artifact into an
unprivileged nginx edge. Only `127.0.0.1:8080` is published. The edge serves `/`,
routes `/v1`, `/health`, `/ready` and `/openapi.json` to the API, gives hashed assets
immutable one-year caching and keeps HTML revalidatable. The browser has no
environment variables or secrets. The API gets only the read-only database password;
the migration job gets only the migration password. PostgreSQL and the API stay on an
internal Docker network.

```bash
docker compose -f docker-compose.rehearsal.yml up --build --wait
uv run --locked watergeo-demo-smoke http://127.0.0.1:8080 --explorer
docker compose -f docker-compose.rehearsal.yml down
```

The local database does not offer hostname-verified TLS, so this topology rehearsal
does not set `WATERGEO_SERVICE_ENVIRONMENT=production`. A real deployment remains
fail-closed: explicit trusted hosts, provider CA, `verify-full`, private database
networking and external HTTPS termination are mandatory. Uvicorn continues with
proxy-header trust disabled. nginx preserves the original Host but does not assert
client addresses or schemes to the application. No CORS rule is required.

## Database bootstrap, backup and restore

Run migrations as a one-shot job before API rollout. Load accepted data only through
the operator/bootstrap path. The API never migrates or publishes data.

`scripts/rehearse_backup_restore.sh` operates only when
`WATERGEO_DISPOSABLE_REHEARSAL=1` is set and both explicitly named containers begin
`watergeo-v1-rehearsal-`. It refuses to overwrite a dump. It uses `pg_dump -Fc`, restores
with `pg_restore --exit-on-error`, verifies revision `0011`, and compares a stable
signature across snapshot IDs, hashes and provenance rows. It reports dump bytes and
wall-clock backup/restore seconds as local measurements. Populate two isolated
containers, set their names, run the script, then point an API container at the
restored database and require `/ready` plus `watergeo-demo-smoke --complete`.

Never use the normal `watergeo-db-1` container. The script intentionally rejects that
name. Evidence storage requires a separate restore/replay check: verify every object
in `evidence-index.json`, replay an accepted bundle offline and require an existing or
verified no-op publication result.

The recorded Phase 12 run, including build sizes and local backup/restore timings, is
in [the rehearsal measurements](../performance/phase-12-v1-rehearsal.md).

Upgrade sequence: independent backup, migration job, readiness, API/edge rollout,
then smoke. Roll back the application image when the schema remains compatible. For
an incompatible database change, restore to a separate database and switch only after
verification; an Alembic downgrade is not assumed to be the production recovery plan.

## Scheduling decision

Use provider-native, non-routable operator jobs on the same private network as the
database. This avoids exposing PostgreSQL or building private-network access from
GitHub-hosted runners. Keep the current UTC cadences: Hydrology hourly at minute 17,
Thames at minutes 7, 22, 37 and 52, and Water Quality metadata daily at 02:43. Enable
each only after a manual job succeeds. Do not schedule global Hydrology history or
Water Quality observations. GitHub workflows remain useful reference/manual
contracts, but production should use them only if defensible private connectivity is
later established.

## Hosting and cost decision — 27 September 2026

DigitalOcean App Platform plus Managed PostgreSQL and Spaces remains the simplest v1
fit: same-provider private connectivity, managed HTTPS, non-routable scheduled jobs,
PostGIS, provider backups and S3-compatible versioned evidence. App Platform jobs are
billed only while running. The first estimate, before tax and domain costs, is:

| Item | Approximate monthly USD |
| --- | ---: |
| API container, 512 MiB–1 GiB | $5–10 |
| Managed PostgreSQL, 1–2 GiB | $15.15–30.45 |
| Spaces evidence/archive storage | $5 base |
| Scheduled operator runtime | $1–10, workload dependent |
| Extra backup/export storage and traffic | $0–10 at small v1 volume |
| Domain | roughly $1–2 monthly when annual fee is apportioned |
| **Expected small-v1 range** | **$27–67/month** |

Traffic beyond included allowances, database growth, longer refresh runtimes and
higher availability can raise this. Confirm the calculator, region, PostGIS version,
private-network and backup terms before purchase. Cloud Run/Cloud SQL remains a sound
alternative but adds IAM and networking surface; Render's documented internal TLS
model previously conflicted with WaterGeo's `verify-full` contract. A self-managed
Droplet is cheaper only by transferring patching, PostGIS, backup and restore risk to
the operator.

Current official references: [App Platform pricing](https://www.digitalocean.com/pricing/app-platform),
[Managed PostgreSQL pricing](https://www.digitalocean.com/pricing/managed-databases),
[Spaces pricing](https://www.digitalocean.com/pricing/spaces-object-storage), and
[scheduled jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/).

## Actionable monitoring

| Signal | Operator action threshold |
| --- | --- |
| API 5xx / latency | page on sustained 5xx or readiness failure; investigate sustained latency against a measured baseline |
| API restarts | investigate repeated restarts or any restart loop |
| Database | page on unavailable/PITR-backup failure; warn on connection or storage trend above 80% |
| Refresh | alert on failure/timeout; investigate repeated advisory-lock skips; alert when configured freshness becomes stale |
| Evidence | page on archive or SHA read-back failure because publication is blocked |
| Migration | page on any failed deploy-time migration; do not roll API forward |

Provider-native metrics, logs and alerts are sufficient for first v1. Record an owner,
destination and tested runbook link for every page before go-live.

## Remaining external work

Choose region/domain and RPO/RTO, provision private resources, store separate secrets,
enable object versioning, run the complete backup/restore and accepted-evidence replay,
configure alerts, manually verify each refresh, then enable schedules. Fabric support
has no new code blocker: a future tenant test still uploads an unchanged validated
bundle, validates checksums in the notebook, writes consumer-owned Delta with
`errorifexists`, queries it and retains snapshot/provenance identity.
