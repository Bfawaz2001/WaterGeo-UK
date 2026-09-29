# Environment Agency flood warnings and areas

## Accepted publisher contract

- **Publisher:** Environment Agency.
- **Official service:** [Flood Monitoring API reference](https://environment.data.gov.uk/flood-monitoring/doc/reference), including `id/floods`, referenced `id/floodAreas/{id}` records and official polygon responses.
- **Licence:** Open Government Licence 3.0 returned by API version 0.9.
- **Identity:** publisher warning URI and `floodAreaID` / area `notation`.
- **Severity:** exact publisher levels 1–4 and labels. WaterGeo does not calculate or reinterpret risk.
- **Time:** `timeRaised`, `timeMessageChanged` and `timeSeverityChanged` are retained as publisher timestamps; retrieval time is separate.
- **Geometry:** official GeoJSON Polygon/MultiPolygon coordinates in WGS84. Geometry must be present, non-empty and valid.

The reviewed live warning set contained three official polygons with ring
self-intersections. Policy `ea-flood-area-structure-v1` applies deterministic GEOS
structure repair only when the result remains polygonal and valid, relative planar area
change is at most `1e-6`, and Hausdorff distance is at most `0.0001` degrees. Source and
canonical WKB hashes, validity reason, area/distance changes, parts and holes are stored.
Anything outside that envelope fails closed; exact publisher GeoJSON remains in evidence.

The current warning feed is transient. The publisher describes a roughly 15-minute update cycle and may retain “warning no longer in force” records for about 24 hours. A WaterGeo snapshot therefore describes only its accepted retrieval.

## Safety and evidence

WaterGeo is not an emergency warning service and offers no service guarantee. Users must use the [official flood warning service](https://check-for-flooding.service.gov.uk/) for safety decisions. The API, explorer and static publication repeat this caveat and expose retrieval time and attribution.

The raw warnings response and every referenced area and polygon response are durably written before validation. Only a complete accepted bundle can load atomically. Hosted retrieval runs at `:02/:17/:32/:47` UTC only when `WATERGEO_FLOOD_SCHEDULE_ENABLED=true`; the public static profile remains a daily snapshot.

## Local acceptance on 29 September 2026

The bounded official response produced 19 warnings and 19 referenced flood areas with
geometry. All were accepted; three areas used the reviewed structure-repair policy and
none were skipped.
