# Phase 7 browser explorer architecture

Date: 2026-09-25

## Decision

The first-party explorer is a separate static application in `web/`, built with
React, strict TypeScript, Vite and MapLibre GL JS. Node 24.15 is the CI baseline:
Node's official release table identifies v24 as LTS while v26 is still Current on
the decision date. The Python package and API runtime image remain unchanged.

Production uses one public origin. Static files serve `/`; ingress forwards
`/health`, `/ready` and `/v1/*` to FastAPI. Browser requests use relative paths,
same-origin credentials and redirect rejection. Local Vite proxies those paths to
`http://127.0.0.1:8000`, so backend CORS stays disabled.

`VITE_API_BASE_PATH`, when used for a path-prefixed same-origin deployment, must be
an absolute path. Schemes, protocol-relative values and browser credentials are
rejected. No `VITE_*` value may be a secret.

## Data behavior

- Hydrology, Water Quality and reservoir points use existing bounded nearby routes.
  Map movement waits 350 ms, aborts the preceding request and replaces results only
  when the newest generation completes. The UI clearly labels the 100-result cap.
- Water Quality and reservoir requests pin the first returned snapshot for the
  session. A different returned identity fails closed and clears the pin for a
  deliberate clean retry. Hydrology nearby has no snapshot selector; complete pages
  replace rather than merge, so identities are never silently combined.
- Water-supply polygons are demand-loaded: map click calls `areas/at-point`, retains
  every overlap/boundary match, then fetches only the chosen reviewed geometry.
- Water Bodies use 100-item keyset pages pinned to one snapshot. Detail and existing
  publisher geometry load together and must match that snapshot. Features are not
  dissolved.
- Source status loads independently of map results. Dataset metadata carried by the
  response supplies publisher, snapshot, licence, attribution and caveats.

No cross-source spatial relationship is created. There are no new API routes,
unbounded bbox reads, vector tiles, browser API keys, analytics, geolocation, Redis,
server cache or materialized views.

## Basemap

The development default is OpenFreeMap's Liberty style at
`https://tiles.openfreemap.org/styles/liberty`. Its official documentation permits
the public instance without registration or API keys and requires attribution;
MapLibre renders the style's attribution control. The service has no SLA and is
provided as-is. Set `VITE_BASEMAP_STYLE_URL` to another reviewed style for deployment,
or set it to an empty value for WaterGeo's local context-free fallback. A failed
remote style also falls back without hiding WaterGeo's own layers.

References:

- [Node.js releases](https://nodejs.org/en/about/previous-releases)
- [OpenFreeMap usage and attribution](https://openfreemap.org/)
- [OpenFreeMap terms](https://openfreemap.org/tos/)
- [OpenFreeMap quick start](https://openfreemap.org/quick_start/)
- [MapLibre attribution control](https://maplibre.org/maplibre-gl-js/docs/API/classes/AttributionControl/)

## Security and accessibility

Responses are capped at 10 MiB in the browser; the server's tighter geometry caps
still apply. External links render only when their parsed protocol is HTTPS. Publisher
text is rendered as React text, never HTML. Major controls are semantic buttons,
checkboxes and labelled regions with visible keyboard focus. Selection and source
information exists outside the canvas. Colour is reinforced by labels and status text.

Camera, active layers and a bounded stable selection identity are stored in the URL.
Coordinates, zoom, layer names, identity format and length are validated before use;
responses never enter the query string.
