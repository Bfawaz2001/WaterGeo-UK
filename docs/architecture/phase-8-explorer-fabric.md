# Phase 8: explorer and portable exports

Decision date: 2026-09-26. Baseline: `f387b2b628e82c1b2f092f0a519feab5cf677c0b`.

WaterGeo remains an independent PostGIS/FastAPI application. Fabric is an optional
consumer of files, not a dependency of the API, refresh jobs, or explorer. The
existing 33 GET routes and SDK/CLI query contracts are preserved.

## Explorer

The map takes the space previously reserved for the permanent details column.
Layer controls collapse with a keyboard-accessible button. Details float above
the map and become a bottom sheet on smaller screens. ResizeObserver keeps the
canvas in sync when the panel changes width. The mobile layer panel overlays the
full-height map instead of pushing it down the page.

Nearby points stay visible while the next debounced query runs. Status explicitly
labels them as previous results. Snapshot mismatches still remove the affected
layer. The accessible result list offers the same selections without canvas use.

Hydrology detail shows accepted measures, original units and timestamps, with a
measurement filter scoped to that station. Sampling-point detail shows original
publisher metadata. Reservoir detail shows the first 20 dated edition readings.
Every detail response must match the selected snapshot. Requests are cancelled
when selection changes. No history is invented from a station or sampling point;
bounded observation retrieval IDs remain an explicit API/CLI workflow.

Water Body type and text filters are explicitly limited to loaded pages, with
loaded/matching counts and continuation available even while filtering. No nearby
filter is advertised as a national search. Layers and their colours form the legend;
labels carry the meaning independently of colour.

## Delivery boundaries

The first scalable layer is the national water-supply overview. The exporter uses
the existing SDK to request every reviewed geometry, verifies snapshot/presentation
policy consistency and checks the dataset again at the end. It never reads or
transforms canonical database geometry directly. GeoJSON retains API properties
and presentation metadata. GeoParquet encodes the same coordinates as WKB.

Tippecanoe builds MVT in PMTiles from those reviewed GeoJSON features. This is a
separate presentation derivative: zoom 0–8, clipping, quantization and simplification.
It must not be used for analytical boundaries, legal supplier lookup or to replace
ADR 0006 output. Small features/holes can disappear at overview scale. Map clicks
still perform the existing exact at-point lookup, preserving overlap semantics.

Each export is a new directory with full dataset provenance and SHA-256/byte counts
for every artifact. Files are staged and the directory published only after success.
Existing directories are refused. There is no mutable `latest` archive. Operators
configure a snapshot-specific same-origin manifest path; mandatory attribution is
shown in both the control and map. Hosts must preserve HTTP Range requests.

No tile server, Redis, MLT, backend cache, spatial inference or Fabric SDK is added.
PyArrow is an optional `exports` extra. Only export CI installs it; the API image
continues installing base dependencies. Water Body PMTiles and dynamic point exports
are deferred pending a separate measured use case; their existing workflows remain.

## Official references

- [PMTiles for MapLibre](https://docs.protomaps.com/pmtiles/maplibre)
- [Tippecanoe creation workflow](https://docs.protomaps.com/pmtiles/create)
- [MapLibre GeoJSON tiling and simplification](https://maplibre.org/geojson-vt/)
- [GeoParquet 1.1](https://geoparquet.org/releases/v1.1.0/)
- [Fabric Maps tilesets, preview](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/map/about-tile-sets)

These formats are compatible export targets. No Fabric tenant, public host or
external deployment has been provisioned or verified by this phase.
