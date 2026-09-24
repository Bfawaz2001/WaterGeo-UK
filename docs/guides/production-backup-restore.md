# Production backup, evidence retention and restore

## Protected assets

- PostgreSQL/PostGIS holds canonical snapshots, source metadata, transformation
  provenance, refresh state and Alembic revision.
- Raw source evidence is equally required for audit and exact replay. Upstream
  continued availability is not a backup.
- Repository history and immutable GHCR digests preserve code, migrations and
  configuration templates. Secrets belong only in the platform secret manager.
- Operational logs support diagnosis but do not replace data/evidence backups.

## Policy to set before go-live

Enable provider daily backups and point-in-time recovery. DigitalOcean currently
documents daily backups with a seven-day window, so add encrypted, versioned object
storage for evidence and periodic logical database exports if the approved recovery
point/retention exceeds that window. Select and record concrete RPO/RTO and retention
periods before provisioning. Restrict backup/evidence read and delete access to named
operators, enable deletion/version protection, and audit restore/download actions.

Do not store database dumps or raw bundles in Git, container layers, application logs
or a public bucket. Keep a separate encrypted copy or provider/account failure plan.
Deleting a managed database can delete its provider backups; require an independent
verified export before destructive changes.

## Disposable restore rehearsal

Run at least quarterly and before a risky migration:

1. Record source database version, enabled PostGIS version, Alembic revision, backup
   timestamp, image digest and expected representative snapshot IDs/counts/hashes.
2. Restore the provider backup to a new isolated database; never overwrite production
   for a rehearsal. Recreate/verify separate roles and trusted-source rules.
3. Connect using the provider CA and `verify-full`. Confirm `postgis` is enabled and
   `SELECT version_num FROM watergeo.alembic_version` returns the expected revision.
4. Run read-only integrity checks and compare recorded dataset counts, snapshot IDs,
   canonical hashes and presentation provenance. Confirm app-role writes fail.
5. Start the recorded compatible API digest against the restored database. Require
   `/ready`, all integration checks suitable for the copy, and the deployment smoke
   command with a representative data endpoint.
6. Retrieve a sample evidence bundle from object storage, verify its stored checksum,
   and perform an offline exact retry in another disposable database. It must return
   `existing`/verified no-op after the original restore is loaded.
7. Record duration, deviations and cleanup. Destroy only the disposable restore after
   evidence is captured; never log secrets or raw connection strings.

A provider dashboard saying “backup complete” is not restore proof. Public go-live is
blocked until one end-to-end restore rehearsal passes and an operator owns future tests.
