# Explorer data interpretation

The map places independent public datasets in a common visual workspace. Proximity,
containment or overlap on screen does not create a WaterGeo relationship.

- **Hydrology stations:** latest observations can be missing or old. Retrieval time
  is not observation time. Measurement cards retain the publisher measure identity,
  unit and declared period; similarly named measures are not combined. Nearby results
  exclude the one accepted station without a publisher location in the measured snapshot.
- **Rainfall gauges:** publisher names are shown when accepted and otherwise the exact
  gauge ID is used. WaterGeo does not infer names or precise coordinates. Zero is a
  reading; missing means no accepted latest reading. Period, observed time and retrieval
  time remain separate, and the snapshot is not an unlimited history archive.
- **Water Quality sampling points:** points describe sampling metadata, not water
  safety or a current result. The public static artifact does not contain an observation
  series. Publisher region fields are not WaterGeo catchments or company service areas.
- **Bathing waters:** annual classifications use the exact publisher vocabulary and
  assessment year. Classification is distinct from an individual sample, short-term
  advice and a daily safe-to-swim judgement.
- **Reservoirs:** locations and values are from a dated 2025 Severn Trent edition.
  Points are not reservoir footprints. Percentage is not a restriction, safety or
  supply-risk classification and should not be compared across companies.
- **Water supply:** the April 2024 Ofwat snapshot is an analytical boundary release.
  A point can return multiple areas at overlaps or shared boundaries. A match does
  not establish a property's current legal supplier. Premises exceptions, coastlines,
  omitted islands and later appointment changes can matter.
- **Water Bodies:** features retain the publisher hierarchy and geometry parts.
  WaterGeo does not infer that a station, sampling point, reservoir or company belongs
  to the selected Water Body.

The **Rivers & Catchments** browser exposes the publisher path River Basin District →
Management Catchment → Operational Catchment → Water Body. Its in-panel filters apply
only to loaded snapshot-pinned pages. Global search is the supported way to find a named
Water Body outside those loaded pages.

Nearby point layers show at most the nearest 100 records within the route's supported
radius. At wide zoom levels they are a bounded sample around the centre, not every
point visible in the viewport. Pan or zoom to request another bounded result set.
Bathing-water classification counts apply after this bounded nearest selection and are
therefore loaded-result counts. Company headings in search group returned supply-area
matches for readability; they do not claim a complete company-area inventory, and every
publisher area remains individually selectable.

Selecting an area shows that one publisher-defined dated polygon in a **Selected
supply area** section. Any company-performance measures are displayed separately and
apply to the company/reporting period, not specifically to that polygon. Starting a
global search clears earlier map-click boundary matches so two discovery paths are not
presented as one result. A complete multi-area company overview is not implemented:
the bounded search response cannot establish completeness, and WaterGeo does not union
or dissolve the first returned polygons into a misleading company boundary.

Use the details panel for publisher, licence, snapshot, retrieval time, attribution
and caveats. Shared URLs contain map state and stable identifiers, not API responses
or precise device location. Supported flood and bathing filters are included. The
explorer does not request browser geolocation, and a copied local-development URL is
not a public share link.
For dynamic products, “current by policy” describes WaterGeo retrieval age against an
operator-configured threshold. It does not describe publisher observation freshness.
Static publication time, retrieval time and observation time are displayed as separate
facts when the corresponding accepted fields exist.
