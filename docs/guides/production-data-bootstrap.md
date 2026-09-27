# Production data bootstrap and refresh

The API image is intentionally API/migration-only. Use the dedicated operator image or
an exact Git commit with `uv sync --locked --extra evidence-s3`. Give the job only the
ingestion role, verified database TLS and outbound HTTPS to the reviewed publisher.
Use an ephemeral working directory and never reuse API service secrets.

## Evidence gate

Every fetch creates source evidence below ignored `data/raw/`. The combined refresh
command now enforces this order:

1. let the fetch and validation complete;
2. calculate and record the bundle/manifest hashes already produced by the client;
3. upload the complete immutable directory to private, encrypted, versioned object
   storage under a content-addressed source/disposition identity;
4. verify the uploaded object's size and checksum by reading it back;
5. load the exact retained directory with the ingestion identity;
6. record snapshot/retrieval ID, evidence key/hash/version, source commit and job ID.

Production mode cannot start with the local backend. Object-store or checksum failure
prevents publication. Raw rejected bundles are retained under `rejected` when files
exist and can never satisfy a source loader.

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
| 6 | Thames Water discharge status | Manually run and verify one durable refresh, then enable its gated schedule. | Dynamic publisher indication; latest WaterGeo retrieval, not continuous streaming. |

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

Static/versioned sources are Ofwat, Catchments and the Severn Trent edition. Dynamic
sources are Hydrology latest, Water Quality sampling-point metadata and Thames status.
Hydrology history and Water Quality observations remain bounded/on-demand. Enable each
dynamic schedule only after its manual durable refresh succeeds.
