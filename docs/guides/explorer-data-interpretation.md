# Explorer data interpretation

The map places independent public datasets in a common visual workspace. Proximity,
containment or overlap on screen does not create a WaterGeo relationship.

- **Hydrology stations:** latest observations can be missing or old. Retrieval time
  is not observation time. Nearby results exclude the one accepted station without
  a publisher location in the measured snapshot.
- **Water Quality sampling points:** points describe sampling metadata, not water
  safety or a current result. Publisher region fields are not WaterGeo catchments or
  company service areas.
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

Nearby point layers show at most the nearest 100 records within the route's supported
radius. At wide zoom levels they are a bounded sample around the centre, not every
point visible in the viewport. Pan or zoom to request another bounded result set.

Use the details panel for publisher, licence, snapshot, retrieval time, attribution
and caveats. Shared URLs contain map state and stable identifiers, not API responses
or precise device location. The explorer does not request browser geolocation.
