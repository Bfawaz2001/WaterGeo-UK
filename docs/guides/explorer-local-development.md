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

The MVP uses Vitest and Testing Library for its browser-facing smoke paths rather
than installing a second browser runtime in CI. Those tests cover the map shell
boundary, layer changes, selections, geometry requests and provenance with a mocked
MapLibre component and deterministic API. A small real-browser E2E check is deferred
until deployment routing exists, when it can also verify the same-origin ingress
contract instead of duplicating component coverage.
