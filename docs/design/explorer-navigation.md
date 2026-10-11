# Explorer navigation and map reliability

## National orientation, bounded detail

The initial broad map looked sparse because point layers query around the map centre,
not across the nation. Hydrology, rainfall and Water Quality cap radius at 100 km;
bathing waters, reservoirs and Thames at 200 km. Each displays at most 100 nearest
results. Clusters count those returned points only.

Phase 17B adds named regional orientation buttons, explicit coverage text and a
national-to-local explanation before layer controls. Region extents are navigation
aids, not authoritative coverage boundaries or density estimates. Search, regional
navigation and cluster expansion lead to bounded local data and selected detail.
**There is no new nationwide point-distribution layer.** Scotland navigation does
not imply Scottish coverage for England-only products.

Phase 18A retains this one-shot navigation contract and improves the path from region
buttons to bounded layer results. Bathing-water classification filters can fit matching loaded points once. They
operate after the bounded nearest-100 query and label both the match count and scope;
they do not represent all classified bathing waters nationally. Search groups returned
water-supply areas under their verified company label without collapsing identities or
claiming the bounded response is a complete company inventory.

The existing optional water-supply PMTiles overview remains under “Coverage and
overview”, configured via its reviewed same-origin export manifest. It is labelled
as a simplified derivative; selected geometry remains exact reviewed GeoJSON. It
does not supply a nationwide point overview. See [geospatial model](../architecture/geospatial-model.md).

## Filter and selection intent

- Water Body selection from either global search or Rivers & Catchments clears a
  previous point focus, preserves every returned publisher geometry component and
  issues one bounds-navigation intent. Manual pan/zoom and later data changes do not
  refit it. Missing/empty accepted geometry leaves the camera unchanged and produces
  a visible message rather than an invented location.
- Flood severity selection filters the loaded accepted warning snapshot and fits
  matching geometry only when data is available, not loading/failed. The explicit
  “Show matching warning areas” action can navigate after loading completes.
- Empty matches leave the view unchanged. A selected detail retains its original
  snapshot even if the list filter excludes it.
- Thames filters remain server-side before bounded nearest results. “Show loaded
  monitor matches” fits only those loaded points, not all national matches.
- Navigation uses one intent ID. Data changes, manual pan/zoom and layer toggles do
  not repeat that fit. `moveend` still triggers the existing bounded query pipeline.
- Point fits use a capped zoom; multipart geometries use bounds. Missing/nonfinite
  coordinates do not become arbitrary map targets. Animations respect reduced motion.
- Nearby lists, labelled selects and buttons provide keyboard alternatives to map
  interaction. Detail remains separate from the scrollable control panel.
- Bathing-water points use publisher classification colours plus written classification
  labels and accessible controls, so meaning does not depend on colour alone.

## Shared view URLs

“Copy view” serializes bounded camera coordinates, zoom, visible layers, supported
selection identity, flood severity and bathing classification. It does not serialize
API responses, credentials or browser location. Clipboard success and failure are
announced; blocked clipboard access exposes the same URL for manual copying. A
localhost/127.0.0.1 URL is explicitly local to that computer. WaterGeo does not
silently substitute a public URL because Pages may contain another accepted snapshot.
Restoration remains snapshot-aware and degrades visibly when a selected identity is
not available in the target publication.

## Publisher flood states

| Level | Display label | Meaning |
| --- | --- | --- |
| 1 | Severe Flood Warning | Publisher severity 1 |
| 2 | Flood Warning | Publisher severity 2 |
| 3 | Flood Alert | Publisher severity 3 |
| 4 | Warning no longer in force | Retained publisher warning; not an active warning |

“All accepted warning states” includes level 4. Unknown/null levels, if encountered
in a warning representation, stay in All and are not assigned a severity. Current
ingestion validates the exact 1–4 vocabulary; this display behavior does not relax it.
An area with no warning is not a warning-state match. Color supplements text and
does not imply a WaterGeo risk calculation. Static and API modes apply the same
filter to their accepted warning representation. Retrieval and publisher timestamps
remain distinct. Always use [official EA guidance](https://check-for-flooding.service.gov.uk/)
for safety decisions.

## OpenFreeMap and fallback

The configured default is [OpenFreeMap Liberty](https://openfreemap.org/quick_start/).
Its style uses Noto Sans fonts. WaterGeo cluster symbols now explicitly request
`Noto Sans Regular` instead of inheriting MapLibre's Open Sans/Arial default, which
does not match that style's supplied font stack. Attribution remains enabled.

Fallback remains a context-free style when basemap loading fails. Restoration waits
for `style.load`, with its listener registered before `setStyle`; teardown removes
pending listeners and guards late callbacks. Initial `load` synchronization is
unchanged. A fallback message is visible: errors are not silently treated as success.

Tests use synthetic WaterGeo data and offline basemap fixtures. External style/tile
availability is not guaranteed by those tests. Upstream shield-expression warnings
and extension-injected console messages must be diagnosed separately in a clean
browser; no upstream style copy or broad console suppression is introduced here.

### Local validation, 11 October 2026

A clean headless Chromium session against the local explorer used 25 synthetic
stations and the real Liberty basemap. The supported Noto Sans glyph request returned
200; the inherited Open Sans/Arial request returned 404. After the correction, all
19 observed OpenFreeMap responses succeeded, the map showed two 12-point clusters
and one station, and no page/console errors or fallback occurred. Screenshots at
1440×1000 and 390×844 had no horizontal document overflow. Chromium emitted only
GPU readback warnings during screenshot capture. No extension was installed;
upstream shield-expression warnings were not reproduced in this viewport.

That check also exposed a synchronization issue: `isStyleLoaded()` can be false
while an already-installed GeoJSON source updates. React effects could then discard
new point data or a camera intent. Source installation after initial `load` or
fallback `style.load` now gates those effects, so data/visibility updates still apply
while tiles are processing. Regression coverage includes actual map-feature selection,
source updates during processing and one-shot camera intent. No glyph rewriting,
upstream style replacement or blanket error suppression was added.
