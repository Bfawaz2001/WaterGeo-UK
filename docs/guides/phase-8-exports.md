# Build and use a portable water-supply bundle

Start the local API with its reviewed Phase 1 snapshot loaded, using the existing
developer guide. GeoJSON export requires only normal WaterGeo dependencies:

```sh
uv run --locked watergeo-export --base-url http://127.0.0.1:8000 \
  --output data/exports/water-supply/review-1
```

For GeoParquet and PMTiles, install the optional export extra and separately install
[Tippecanoe](https://github.com/felt/tippecanoe). The measured build uses release
2.79.0 at `68ab8dcc229f95b8b25877697d5e8d66783af503`.

```sh
uv sync --locked --extra exports
uv run --locked --extra exports watergeo-export \
  --base-url http://127.0.0.1:8000 \
  --output data/exports/water-supply/review-2 \
  --parquet --tippecanoe /absolute/path/to/tippecanoe
```

The command writes `water-supply.geojson`, optional `water-supply.parquet`, optional
`water-supply.pmtiles`, and `manifest.json`. The manifest retains source SHA-256,
snapshot UUID, original licensing uncertainty, attribution, canonical transformation
version and separate presentation version. Artifact hashes identify exact bytes.
GeoJSON preserves the API geometry; its serialization is not the original publisher
archive or the PostGIS text used by the API geometry hash. GeoParquet WKB uses
longitude/latitude (CRS84), declared by GeoParquet's default CRS semantics.

The process makes bounded SDK requests, up to 2,000 records/20 pages, and checks
the complete expected count. One selected-area geometry is fetched at a time. A
failed snapshot/policy check or tile build publishes no bundle. Rebuild to a fresh
directory after an accepted source change; never modify a published archive in place.
Retain the raw publisher evidence independently of these exports.

## Optional local overview

Copy a completed bundle into the ignored `web/public/exports/<snapshot>/` directory.
Set the following in `web/.env.local`, substituting the real snapshot folder:

```text
VITE_WATER_SUPPLY_OVERVIEW=/exports/<snapshot>/manifest.json
```

Restart Vite, then enable **Water-supply overview**. This control appears only when
configured. It shows the snapshot and attribution. The archive is read by HTTP Range;
production static hosting must return `206 Partial Content`, preserve byte offsets,
and avoid transparent whole-file compression of `.pmtiles`. Keep manifests and
archives on the same origin. No CORS or browser credentials are needed.

The overview is for orientation. Enable **Water-supply lookup** and click the map
to get all exact matches, then select one reviewed API polygon. The archive may be
older than the current API; its separate snapshot label makes that distinction explicit.

Measure an export locally with:

```sh
cd web
node scripts/measure-overview.mjs ../data/exports/water-supply/review-2
```

This reports local reads and parse timings, not network latency or GPU rendering.
PMTiles deliberately omits most descriptive attributes; retrieve details from the
API or the exact GeoJSON/Parquet bundle.
