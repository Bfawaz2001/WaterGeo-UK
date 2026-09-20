# Scheduled Hydrology latest refresh

Phase 2 is implemented end to end: ingestion → validation → storage → API → freshness
→ refresh scheduling. This is deployable repository infrastructure, not a claim that
a production database, API or alerting service has been deployed.

## Workflow and cadence

`.github/workflows/hydrology-refresh.yml` runs **Hydrology latest only** with
`workflow_dispatch` and cron **`17 * * * *`**: minute 17 of every hour, UTC. This is
a conservative WaterGeo operator policy, not an Environment Agency SLA. GitHub can
delay or drop scheduled runs; public repository schedules can also be disabled after
inactivity. See [GitHub schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The 30-minute CLI deadline leaves time for setup, cleanup, artifact upload and summary
within a 40-minute job limit. The workflow runs the existing command:

```sh
uv run --locked python scripts/refresh_sources.py hydrology --timeout-seconds 1800
```

It does not schedule Ofwat, catchments or bounded history. It does not run migrations
or install a database. There is no embedded scheduler or alternate ingestion path.

Refresh cadence and stale thresholds are independent. Configure the API's
`WATERGEO_HYDROLOGY_RETRIEVAL_MAX_AGE_SECONDS` and
`WATERGEO_HYDROLOGY_OBSERVATION_MAX_AGE_SECONDS` separately for your service needs.
A successful retrieval can contain old, missing or null observations. The workflow
reports refresh success; it does not promise current observations or run a second
status command. Use `/v1/sources/status` for the accepted-data view.

## Enable safely

1. Provision PostgreSQL/PostGIS using the existing schema and least-privilege roles;
   apply migrations through `0006` separately. Check the API's `/ready` if deployed.
2. Provide a database endpoint reachable from `ubuntu-24.04` GitHub-hosted runners,
   with server TLS enabled and a certificate matching the connection hostname.
   A localhost Compose database or private endpoint without network connectivity will
   not work. Establish an approved network path; do not expose PostgreSQL broadly just
   to accommodate runner addresses. No cloud provider, VPN or hosted instance is assumed.
3. Create the GitHub environment **`hydrology-refresh`**. Restrict its deployment
   branches to `main`; review environment protection rules for unattended schedules.
   Required reviewers, if configured, will require approval on each run.
4. Store the following environment secrets (repository secrets also work). Do not use
   the application, migration or administrator password for ingestion.

   | Secret | Value |
   | --- | --- |
   | `WATERGEO_DB_HOST` | Reachable database DNS name matching the server certificate |
   | `WATERGEO_DB_PORT` | Database port, typically `5432` |
   | `WATERGEO_DB_NAME` | Existing database name |
   | `WATERGEO_INGESTION_USER` | Existing restricted ingestion role, normally `watergeo_ingest` |
   | `WATERGEO_INGESTION_PASSWORD` | Its password, at least 16 characters |
   | `WATERGEO_DB_CA_PEM` | Trusted CA certificate/bundle in PEM form, obtained through a trusted channel |

5. Set the **repository Actions variable** `WATERGEO_HYDROLOGY_SCHEDULE_ENABLED` to
   exactly `true`. It must be a repository variable: job-level conditions are evaluated
   before environment variables become available. Missing/false skips the job without
   connecting to a database. Both manual and scheduled jobs use this switch.
6. After merging the workflow separately, open Actions → **Hydrology latest refresh**
   → Run workflow, select **main**, and inspect the first run, summary and artifact.
   There are no dispatch inputs. Repository and `refs/heads/main` guards prevent this
   workflow's job from running on forks or manually selected feature branches.

The token has only `contents: read`; checkout does not persist credentials. No PR or
push event starts this workflow. All actions are pinned to full commit SHAs. Protect
main and review workflow changes: these guards cannot protect against someone already
authorized to modify trusted deployment code. No secrets were installed by this change.

## TLS contract

The workflow fixes `WATERGEO_DB_SSLMODE=verify-full` and writes the CA secret to a
mode-0600 file under the ephemeral runner temp directory. `WATERGEO_DB_SSLROOTCERT`
points to that file. These settings pass to libpq through SQLAlchemy without putting
passwords in a printed connection string. `verify-full` checks the certificate chain
and hostname; it does not fall back to plaintext. See
[PostgreSQL SSL verification](https://www.postgresql.org/docs/current/libpq-ssl.html).

For local tools you can set the same mode and a CA file path in the environment or
`.env`. Explicit weak TLS modes are rejected. A CA path without `verify-full` is
rejected, preventing an accidentally ignored trust setting. Leaving both unset preserves
existing local Docker/libpq behavior; this legacy default is not a remote TLS guarantee.
Always set verified TLS for remote deployments. Bad/missing CA files, hostname mismatch
and untrusted certificates fail connection; no verification bypass is supplied.

## Concurrency

All manual and scheduled runs share the fixed group `hydrology-latest-refresh` with
`cancel-in-progress: false`. The active run completes; at most one pending run remains,
and a new arrival replaces an older pending run. There is no accumulating backlog and
no promise that every manual request will execute. See
[GitHub concurrency rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

The existing PostgreSQL source lock additionally protects against a cooperating local
CLI or another scheduler using the same database. It remains necessary outside this
repository's Actions concurrency group. Exit 3 (busy), like every nonzero CLI exit,
fails the workflow; it is not silently treated as success.

## Failure visibility and retention

The refresh step preserves the CLI's pipeline exit code; a log write failure also
fails the step. Configuration checks return sanitized fixed events. Only the refresh
CLI's sanitized stdout and fixed setup events enter the log file. Raw stderr is not
retained or printed by the refresh invocation: dependency/setup failures remain visible
in their own Actions steps, while refresh failures expose their exit code and safe logs.

The workflow attempts artifact upload and job summary on success and failure:

- Artifact: `hydrology-refresh-<run ID>-<attempt>`, requested retention **14 days**.
- Exactly one file: `refresh.jsonl`, containing operational JSON logs.
- Summary: source, run ID, refresh outcome, exit code, success indicator, artifact name
  and the note that freshness is separate operator policy.
- No raw evidence, manifests, `.env`, CA file, database dumps or entire directories
  are uploaded. Treat artifacts in this public repository as publicly readable.

An unconfigured, explicitly enabled job fails instead of silently falling back to a
local database. Setup failures show an unavailable exit code/skipped refresh in the
summary. Upload failures also fail the job, even when the refresh itself succeeded.
Hard runner loss, platform cancellation or the job timeout may prevent summary/artifact
finalization; a skipped job produces neither. Repository retention policy can constrain
artifact lifetime. Raw evidence on ephemeral runners disappears when the runner is
destroyed; this workflow does not provide durable raw-evidence retention or offline
retry across runs. Existing accepted database provenance is preserved.

Failed runs are visible in GitHub Actions. There is no new email, Slack, PagerDuty or
other notification integration; GitHub account notification preferences are independent.
External delivery and deployment-specific alert routing remain future operational work.

## Disable and troubleshoot

Set `WATERGEO_HYDROLOGY_SCHEDULE_ENABLED=false` to skip both scheduled and manual jobs.
This does not stop an already running job. To stop timer triggers entirely, disable
the workflow in Actions (also disables dispatch), or remove the schedule stanza via
review while retaining dispatch. Re-enable the repository variable for manual operation.

For a failed run, first inspect the step outcome, summary and artifact. Check secret
presence, network reachability, trusted CA/hostname, schema and ingestion grants without
printing credentials. Codes 1–5 retain the meanings in the
[source operations guide](source-operations.md). A forced stop near commit may have an
uncertain outcome; inspect accepted metadata before rerunning. For a local diagnosis,
use the CLI command above with privately configured ingestion credentials and TLS.

The Phase 2 implementation is complete; live deployment verification awaits real
infrastructure. Phase 3 starts with public water-quality source/licence assessment.
