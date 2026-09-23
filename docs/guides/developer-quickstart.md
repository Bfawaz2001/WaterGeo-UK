# Python SDK and CLI quickstart

WaterGeo has no hosted endpoint yet. Start the API locally using the repository
[setup instructions](../../README.md#local-development), or supply the URL of a
WaterGeo instance that you operate.

## Install from the current project

```bash
uv sync --locked
```

The current `watergeo-uk` distribution contains the API, synchronous client, and
CLI. A smaller standalone client distribution is a possible future packaging task.

## Python client

Always provide a base URL explicitly:

```python
from watergeo.client import WaterGeoClient

with WaterGeoClient("http://127.0.0.1:8000") as client:
    print(client.health().status)
    print(client.readiness().status)
    for source in client.source_status().sources:
        print(source.source, source.availability)
```

The client accepts HTTP and HTTPS for self-hosted and local use. It rejects embedded
credentials, query strings, and fragments. Redirect following and environment proxy
inheritance are disabled. Requests have a timeout and successful response bodies
have a 16 MiB default limit. A custom `httpx2` transport can be injected for tests.

### Lists, nearby searches, and snapshot pinning

Manual page methods expose the API cursor directly:

```python
with WaterGeoClient("http://127.0.0.1:8000") as client:
    page = client.hydrology_stations(limit=25)
    next_page = client.hydrology_stations(
        limit=25,
        after_id=page.next_after_id,
        snapshot_id=page.dataset.snapshot_id,
    )

    nearby = client.water_quality_sampling_points_near(
        lon=-2.0, lat=52.0, radius_m=20_000, limit=10
    )
```

Iterators request the maximum normal page size, automatically reuse the first page's
snapshot, reject non-advancing cursors, and stop at 1,000 pages or 100,000 records by
default:

```python
with WaterGeoClient("http://127.0.0.1:8000") as client:
    for station in client.iter_hydrology_stations(max_records=5_000):
        print(station.station_id, station.labels)

    for point in client.iter_water_quality_sampling_points(max_records=70_000):
        print(point.sampling_point_id, point.location_status)
```

The same pattern is available for water-supply areas, every Catchment hierarchy
list, sampling points, reservoirs, Hydrology history, Water Quality observations,
and reservoir readings. Nearby searches are already bounded server operations and
do not have fake pagination.

### GeoJSON

GeoJSON stays typed GeoJSON. The SDK does not convert it to Shapely objects or alter
coordinates:

```python
with WaterGeoClient("http://127.0.0.1:8000") as client:
    feature = client.water_supply_geometry(1)
    print(feature.model_dump(mode="json"))

    collection = client.water_body_geometry("GB106027064380")
    print(collection.type, len(collection.features))
```

### Historical and company readings

Retrieval IDs refer to bounded evidence that an operator previously accepted. They
do not trigger publisher ingestion:

```python
from uuid import UUID

retrieval_id = UUID("00000000-0000-4000-8000-000000000001")
with WaterGeoClient("http://127.0.0.1:8000") as client:
    history = client.hydrology_history(retrieval_id, limit=100)
    observations = client.water_quality_observations(retrieval_id, limit=100)
    readings = client.reservoir_readings("1", limit=100)
```

Hydrology timestamps and reservoir timestamps remain aware datetimes. Water Quality
`observed_at_text` deliberately remains text: the publisher does not specify its
timezone. `numeric_value`, `upper_bound`, and `lower_bound` remain separate, and the
client performs no unit conversion. Severn Trent capacity and level fields retain
their publisher units and dated-edition caveats.

### Errors

```python
from watergeo.client import WaterGeoAPIError, WaterGeoError

try:
    with WaterGeoClient("http://127.0.0.1:8000") as client:
        client.hydrology_station("unknown")
except WaterGeoAPIError as error:
    print(error.status_code, error.detail)
except WaterGeoError as error:
    print(error)
```

`WaterGeoTransportError` covers connection and timeout failures.
`WaterGeoAPIError` preserves the status and a bounded API detail for responses such
as 404, 422, and 503. `WaterGeoResponseError` reports an unexpected content type,
oversized body, invalid schema, or unsafe pagination behavior. Error messages do not
include the configured URL or unbounded response bodies.

## CLI

Pass the server explicitly or set it for the current shell:

```bash
watergeo --base-url http://127.0.0.1:8000 health
export WATERGEO_BASE_URL=http://127.0.0.1:8000
watergeo sources status
python -m watergeo hydrology stations --limit 10
```

The global `--pretty` option indents output. Compact deterministic JSON is the
default for shell pipelines:

```bash
watergeo water-supply geometry 1 > area.geojson
watergeo hydrology near --lon -2 --lat 52 --radius-m 20000
watergeo water-quality sampling-points --all --max-records 70000
watergeo severn-trent readings 1 --all
```

Use `watergeo --help` and each nested `--help` page for the full command surface.
Commands cover operations, source status, water supply, Hydrology and history,
Catchments, Water Quality and observations, and Severn Trent reservoir levels.
Normal output goes to stdout; errors go to stderr. Exit status 2 means command-line
usage, 3 transport failure, 4 HTTP API error, and 5 response/configuration failure.

## Provenance and limitations

Inspect each dataset response before using records. It supplies the snapshot or
release identity, hashes, retrieval timestamps, attribution, licence, and caveats.
Third-party data keeps its publisher licence; the repository MIT licence does not
relicense it.

WaterGeo does not infer current suppliers, company/catchment relationships, supply
risk, restrictions, or local dates. It has no authentication contract or public
production deployment in this phase. The SDK and CLI are read-only clients and do
not expose refresh or ingestion operations.
