# Production data bootstrap and refresh

The API image is intentionally API/migration-only. Run source tools from an exact
Git commit with `uv sync --locked` in a separate one-shot job. Give the job only the
ingestion role, verified database TLS and outbound HTTPS to the reviewed publisher.
Use an ephemeral working directory and never reuse API service secrets.

## Evidence gate

Every fetch creates source evidence below ignored `data/raw/`. Before loading it:

1. let the fetch and validation complete;
2. calculate and record the bundle/manifest hashes already produced by the client;
3. upload the complete immutable directory to private, encrypted, versioned object
   storage under `source/run-or-retrieval-id/`;
4. verify the uploaded object's size and checksum by reading it back;
5. load the exact retained directory with the ingestion identity;
6. record snapshot/retrieval ID, evidence key/hash, source commit and job ID.

The current combined `refresh_sources.py` command publishes before an external
object-store upload. Therefore unattended production refresh scheduling remains
disabled until a failure-tested wrapper or dedicated operator image makes durable
evidence a prerequisite for publication. Existing GitHub Hydrology scheduling keeps
operational logs but does not retain raw evidence and is not sufficient for this
production policy.

## Initial sequence

After migrations and before public traffic, process one source at a time. Follow its
linked guide for exact evidence paths and interpretation.

| Order | Dataset | Production action | Lifecycle |
| --- | --- | --- | --- |
| 1 | Ofwat water-supply boundaries | Fetch, validate, retain, then run `scripts/load_ofwat_water_supply.py` | Pinned April 2024 static release; exact retry is a verified no-op. |
| 2 | EA Hydrology latest | Fetch with `scripts/fetch_ea_hydrology.py`, retain, then pass its directory to `scripts/load_ea_hydrology.py` | Dynamic latest snapshot; no history implied. |
| 3 | EA Catchment Data Explorer | Fetch with `scripts/fetch_ea_catchments.py`, retain, then use `scripts/load_ea_catchments.py` | Reviewed Cycle 3 hierarchy; replace only after source review. |
| 4 | EA Water Quality sampling points | Fetch with `scripts/fetch_ea_water_quality.py`, retain, then use `scripts/load_ea_water_quality.py` | Dynamic metadata snapshot. |
| 5 | Severn Trent reservoir levels | Fetch the reviewed source using the bounded refresh client, retain its bundle, then replay with `refresh_sources.py stream-reservoir-levels --evidence-dir …` | Static 2025 edition; never schedule as live levels. |

Hydrology history and Water Quality observations are intentionally scoped retrievals,
not global bootstrap jobs. Request only an explicit reviewed measure/time window or
sampling-point/determinand/date window, retain its evidence, then replay the evidence
directory. Do not scrape all history. See the [Hydrology](hydrology-walkthrough.md),
[Water Quality](water-quality-walkthrough.md), [reservoir](stream-reservoir-levels-walkthrough.md),
and [source operations](source-operations.md) guides.

## Verification

After each load, capture the structured completion event and query its dataset/status
endpoint using the read-only identity. Exact evidence retries must return `existing`
or the source-specific verified no-op; unexpected changed IDs/hashes fail the release.
Finish with `/ready`, `/v1/sources/status`, representative dataset endpoints and the
deployment smoke check. Do not make traffic public with an empty database.

No source beyond Hydrology has an existing schedule. Do not enable new schedules in
Phase 6. When durable evidence transfer is implemented, start with one manually
dispatched refresh, verify retention and database publication, then enable the
separately gated schedule.
