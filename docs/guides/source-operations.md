# Source freshness and refresh operations

Run these commands from the repository root after `uv sync --locked`, database setup
and `uv run --locked alembic upgrade head`. Schema head remains `0006`. The API uses
the read-only application role; refresh jobs use `WATERGEO_INGESTION_PASSWORD` and the
existing ingestion role. Jobs do not require administrator or migration credentials.

## Read source status

```sh
curl --fail http://127.0.0.1:8000/v1/sources/status
```

The endpoint accepts no query parameters. It returns a database `checked_at` timestamp
and four source entries. Missing compatible data is `availability: unavailable` with
null identity/times. A database failure returns a sanitized 503; unavailable data is
still a successful 200 status report. Successful and database-error responses are
`Cache-Control: no-store`. `/health` remains process liveness; `/ready` still checks
PostGIS and schema compatibility, independent of data age.

| Source | Accepted selection | Meaning of age |
| --- | --- | --- |
| `ofwat` | Exact reviewed archive SHA-256 and canonical transformation | Static April 2024/v1_5 release; age is not evidence that a newer release exists. |
| `hydrology` | Latest compatible snapshot by retrieval completion, then descending UUID | Retrieval age and oldest/newest latest-observation ages are separate. |
| `hydrology-history` | Latest compatible retrieval across measures, same ordering | One explicit measure and requested window; not coverage of all historical data. |
| `catchments` | Latest compatible `c3-plan` snapshot, same ordering | Cycle 3 retrieval age, not publisher update time or a newer plan check. |

`snapshot_id` also identifies a historical retrieval. `content_sha256` identifies
accepted source evidence; `normalization_version` is the source contract version
(the canonical transformation version for Ofwat). This endpoint does not replace
dataset endpoints' detailed provenance, including Ofwat presentation policy.
`retrieved_at` is retrieval completion, except Ofwat's recorded retrieval timestamp;
Ofwat has no stored retrieval-start timestamp, so `retrieval_started_at` is null.

### Explicit dynamic policy

Set these optional values in `.env` (host API and Compose both support them), then
restart/recreate the API. The following values are **illustrative operator choices**:

```dotenv
WATERGEO_HYDROLOGY_RETRIEVAL_MAX_AGE_SECONDS=3600
WATERGEO_HYDROLOGY_OBSERVATION_MAX_AGE_SECONDS=86400
```

Choose thresholds from your service's tolerated delay and the measures you ingest.
There is no assumed Environment Agency publication SLA. Each limit accepts 1 through
31,536,000 seconds; unset/empty means `unknown`. Responses expose the effective limits.
An age equal to its limit is `current`; greater is `stale`. Future timestamps have
null ages and cannot establish current status.

Observation status uses the oldest timestamp among each measure's stored latest reading.
Any known reading beyond the limit makes the aggregate `stale`, even if other readings
are missing. Otherwise, missing readings, null values or future readings make it
`unknown`; only complete, non-null readings within the limit make it `current`.
Counts expose null values and measures without readings. This is not a quality judgment
and a single inactive measure can make the aggregate stale. There is no per-station
policy or alert suppression in this milestone.

Available static/versioned sources and history use `not_applicable` for age policy.
History still reports oldest/newest observation times and null-value counts. An old
observation can be entirely correct for its requested historical window. Unavailable
sources have unknown retrieval freshness. No endpoint makes a live publisher request.

## Refresh one source

```sh
uv run --locked python scripts/refresh_sources.py hydrology
uv run --locked python scripts/refresh_sources.py catchments --timeout-seconds 7200
uv run --locked python scripts/refresh_sources.py ofwat
uv run --locked python scripts/refresh_sources.py hydrology-history \
  --measure-id a-flow-i-900-m3s-qualified \
  --from 2026-09-01T00:00:00Z --to 2026-09-02T00:00:00Z
```

The history identifier above is synthetic: substitute a real public measure ID from
the station API. History requires timezone-aware bounds of at most 31 days. Other
sources reject history arguments. No arbitrary source URL is accepted. Ofwat only
accepts the exact reviewed archive; a changed upstream file requires review.

Jobs log JSON to stdout: `refresh_started`, `refresh_phase` (`fetch`, `validate`,
`load`), 30-second `refresh_progress`, and `refresh_complete` (`published`, snapshot
identity, `inserted` or `existing`). Failures expose an error class, never exception
messages, SQL, credentials, evidence paths or manifests. Progress is worker liveness,
not a guarantee that the publisher is making progress. Capture logs in your scheduler.

Online evidence is retained in `data/raw/refresh/<source>/<run UUID>/`; EA clients
place their evidence bundle in a child UUID directory. Ofwat writes its hash-named
archive and manifest directly in the run directory. The raw directory is ignored by
Git. Inspect it locally after completion/failure; do not publish raw logs or credentials.

To retry a verified bundle without fetching again:

```sh
uv run --locked python scripts/refresh_sources.py hydrology \
  --evidence-dir data/raw/refresh/hydrology/RUN_UUID/BUNDLE_UUID
```

Use the corresponding source name for other bundles. For Ofwat pass the directory
containing the hash-named ZIP and JSON. Offline history takes its measure/window from
the verified manifest; do not supply additional history arguments. Missing, partial
or altered evidence fails validation before load. Existing snapshot retries verify
stored content rather than trusting an identity match. Repeated online retrievals can
produce new evidence identities; only a retry of the same evidence promises idempotency.
Refreshing identical Ofwat content keeps its original accepted retrieval timestamp;
status is not a last-successful-poll monitor.

| Exit | Meaning | Scheduler handling |
| --- | --- | --- |
| 0 | Committed or verified existing snapshot | Success |
| 1 | Fetch, validation, database or worker failure | Retain evidence/logs; investigate or back off |
| 2 | Invalid arguments | Correct configuration; `--help` lists syntax |
| 3 | Another cooperating job owns the source lock | Skip or retry later |
| 4 | Wall-clock deadline reached | Inspect evidence and retry safely |
| 5 | Interrupt/termination handled | Inspect outcome before retry |

Deadline defaults to 3,600 seconds; allowed range is 30–86,400. Cleanup allows up to
five seconds after termination and five after forced kill. Existing client request,
byte, retry, pacing and database timeouts remain in force. CDE deliberately runs slowly;
do not defeat publisher pacing by running the old fetch script concurrently.

The worker owns a database session advisory lock across all phases. Same-source jobs
against the same database conflict; different sources can run independently. All history
windows share one lock. A lost lock prevents proceeding to load when detected; existing
transaction locks still serialize publication. This is cooperative concurrency control,
not a distributed fencing guarantee during a database/network partition. SIGTERM/SIGINT
normally stops the worker and rolls back an open transaction; SIGKILL of the supervisor
cannot run cleanup. Configure the scheduler to terminate the entire process group/container.
The worker retains its lock while alive, and disconnected sessions release locks.
Termination near commit can have an uncertain outcome: retry the same retained evidence.

## Schedule externally

Use cron, a container job or another scheduler with a fixed working directory, a
configured Python/uv PATH, private credential injection and retained stdout/stderr.
For example, after choosing an hourly Hydrology retrieval policy:

```cron
0 * * * * cd /srv/WaterGeo-UK && /usr/local/bin/uv run --locked python scripts/refresh_sources.py hydrology --timeout-seconds 1800 >> /var/log/watergeo/hydrology.jsonl 2>&1
```

Adjust paths and permissions to your deployment. Rotate logs and alert on exit codes
and status fields separately. Set scheduler timeout longer than the CLI deadline plus
cleanup. Apply migrations separately and check API `/ready` before enabling jobs;
ingestion permissions intentionally do not include the API's migration-table check.
Do not schedule full CDE/static reloads at observation frequency. Preserve evidence
under an explicit operator retention policy; no automatic deletion is implemented.

There is no durable failed-run table, dashboard, automatic cadence, notification
delivery or publisher revision discovery yet. Source status cannot tell whether the
last attempted refresh failed. Scheduler monitoring and logs fill that gap for now.
See [ADR 0010](../adr/0010-source-freshness-refresh-operations.md).
