# Map explorer local development

## Prerequisites

- Existing WaterGeo Python/Docker prerequisites
- Node.js 24.15 or newer within the Node 24 LTS line
- npm (the committed lockfile is authoritative)

Load whichever reviewed datasets you want to inspect using their existing guides.
The explorer handles unavailable datasets without using live publisher APIs.

## Run locally

Terminal 1, from the repository root:

```sh
docker compose up --wait db
uv run --locked alembic upgrade head
uv run --locked uvicorn watergeo.api.app:create_app --factory --reload \
  --no-access-log --no-proxy-headers
```

Terminal 2:

```sh
cd web
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite forwards only `/health`, `/ready` and `/v1`
to `http://127.0.0.1:8000`. Do not enable backend CORS for this workflow.

## Product workflow

The top-bar search covers current compatible Hydrology stations, Water Quality
sampling points, Severn Trent reservoirs, Thames discharge monitors, Water Bodies
and Ofwat water-supply areas. It searches exact publisher identities and indexed
name prefixes, returns at most 24 results to the explorer, and does not call an
external geocoder. Selecting a result retrieves detail from the exact snapshot
reported by search before moving the map or opening the detail drawer.

Point layers remain server-bounded to the nearest 100 results for the current map
view. MapLibre clusters only those returned points at low zoom; it does not load a
national point collection into browser memory. Cluster counts therefore describe
the current bounded result set, not a complete national count.

Selected Hydrology measures distinguish the publisher observation time from the
WaterGeo retrieval time. Reservoir selections chart percentage readings only within
the same snapshot and unit. The chart does not infer restriction, safety or supply
risk. Exact values remain available below the accessible SVG summary.

## Configuration

The browser uses relative API paths. Optional local `.env.local` values are:

```text
VITE_BASEMAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
# VITE_API_BASE_PATH=/watergeo
```

An explicitly empty `VITE_BASEMAP_STYLE_URL` uses a context-free background and
avoids all third-party tile traffic. A different basemap must be reviewed for usage,
privacy, attribution and cost. Never put a token, password or secret in `VITE_*`.

## Quality checks

```sh
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

The tests use deterministic WaterGeo contract fixtures. They do not call WaterGeo,
OpenFreeMap or publisher services. Production source maps are disabled to avoid
shipping source text; the normal minified assets and immutable build hashes remain.

Vitest and Testing Library cover search, clustering, layer changes, charts,
selection, geometry requests and provenance with deterministic contracts. Playwright
runs the production Vite build against intercepted WaterGeo API fixtures, including
desktop search/detail and narrow-screen controls. Browser tests do not contact live
publisher services or a public WaterGeo deployment.
