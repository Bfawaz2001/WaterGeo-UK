# Fabric compatibility: optional file consumption

WaterGeo can run without Microsoft Fabric. These instructions describe a consumer
workflow in a user's existing Fabric environment; nothing here provisions or
authenticates from WaterGeo. Tenant capacity, preview availability and permissions
must be checked by that user. The local validation package is implemented and tested;
no real Fabric tenant execution is claimed.

## Entity mapping

| WaterGeo entity | Implemented output | Consumer use |
| --- | --- | --- |
| Reviewed water-supply area | GeoJSON Feature; GeoParquet WKB row | Exact feature inspection; notebook analysis |
| Water-supply overview | PMTiles/MVT `water_supply` layer | Fabric Map or WaterGeo overview |
| Thames Water discharge status | Point GeoJSON; GeoParquet WKB and typed status columns | Snapshot analysis, Lakehouse ingestion and Power BI reference points |
| Phase 15 rainfall and bathing waters | GeoParquet WKB with typed measure/classification columns | Lakehouse spatial and freshness analysis |
| Phase 15 flood monitoring | Flood-area GeoParquet plus separate warning Parquet | Spatial areas without losing warning rows |
| Ofwat company performance | Parquet with company, period, measure, value-state and publication columns | Regulatory trend analysis |
| Export dataset/provenance | JSON manifest; Parquet schema metadata and row fields | Snapshot identification, hashes, licensing |
| Hydrology, Water Quality, reservoirs, Water Bodies | Existing bounded API and SDK | Future dedicated exports; no new file exporter claimed |

Stable row identity is `(snapshot_id, source_id)`; IDs are strings in Parquet to
avoid consumer numeric coercion. `properties_json` and `presentation_json` preserve
source notices and reviewed transformation metadata. Geometry is binary WKB, not a
Delta spatial type. A Spark write can make a Delta table while retaining this binary
column, but it does not automatically retain GeoParquet schema metadata: keep the
manifest alongside it and preserve provenance columns.

Phase 15 analytical files also carry `retrieval_id`, `retrieved_at`, publisher and licence.
Rainfall exposes station identity, display name, observation time, value, unit and declared
period. Bathing waters expose identity, classification, assessment year, sample relation and
publisher risk/advice JSON. Flood areas and warnings are separate files so multiple warnings
cannot be collapsed into one geometry row. Company performance preserves missing and
not-applicable states separately from numeric zero. PyArrow remains an optional export
dependency; no Fabric runtime dependency is added.

## Lakehouse / OneLake example

1. Generate and verify a bundle as described in [exports](phase-8-exports.md).
2. In an existing Lakehouse, upload the entire directory under
   `Files/watergeo/water-supply/<snapshot>/`. Preserve filenames and manifest.
3. Use the [notebook example](../../examples/fabric/lakehouse_consumer.py) with a
   default Lakehouse attached. It checks the Parquet hash before reading. Its optional
   table-writing function uses `errorifexists`, so it cannot overwrite a table.
4. Retain one table or partition per snapshot and an explicit accepted snapshot
   selection. Do not append indistinguishable editions into one table.

Before upload, run `python examples/fabric/validate_bundle.py <bundle> --entity
water-supply`. In the tenant, `examples/fabric/tenant_validation_notebook.py` combines
the checksum-reading examples with a consumer-owned `errorifexists` Delta write. Follow
the [real-tenant checklist](production-validation-checklist.md); these files do not
authenticate, upload or provision anything.

OneLake's Files area supports Parquet and other files; managed Lakehouse tables use
Delta. These are separate storage contracts, not interchangeable extensions.
[OneLake Files](https://learn.microsoft.com/en-us/fabric/onelake/create-lakehouse-onelake),
[Lakehouse tables](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-and-delta-tables).

## Fabric Map example (preview)

In an existing workspace, create a Map item through the Fabric UI, add the existing
Lakehouse as a data source, and select the snapshot's `water-supply.pmtiles` file as
an overview layer. Name it **Ofwat April 2024 — simplified overview**. Keep attribution
and snapshot visible. Use exact GeoJSON for a small selected subset when necessary;
avoid feeding the entire national GeoJSON to a raw-file layer.

This is the equivalent manual Map configuration example, avoiding invented item
schemas. Fabric's documented `map.json` supports Lakehouse data sources and file
layer sources; users automating their own environment can follow the current official
definition rather than adopting a stale generated template. No creation request is
made by WaterGeo.
[Map definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/map-definition),
[static Map tutorial](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/map/tutorial-create-fabric-map-python),
[PMTiles support](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/map/about-tile-sets).

Fabric's own PMTiles generation supports zoom 5–18. WaterGeo supplies an existing
0–8 archive for country-scale overview; it does not invoke Fabric's generation job.
Confirm preview consumption in the target tenant before operational adoption.

## Power BI / Azure Maps

Use the exported GeoJSON as an Azure Maps reference layer, preferably a bounded
subset for a report. Keep `source_id` as text in model joins and include snapshot in
the join key. Use the Delta table for attributes, preserve provenance in report
tooltips, and never label area containment as a current property supplier.
PMTiles is not claimed as a Power BI reference-layer input.
[Supported reference files](https://learn.microsoft.com/en-us/azure/azure-maps/power-bi-visual-add-reference-layer).

KQL/Eventhouse integration is deferred: static versioned boundaries do not need an
additional streaming database. Native Delta generation and tenant authentication
remain consumer responsibilities, not core API dependencies.

For Thames status, upload the complete bundle under
`Files/watergeo/thames-discharge-status/<snapshot>/` and use
[`examples/fabric/thames_discharge_consumer.py`](../../examples/fabric/thames_discharge_consumer.py).
The example verifies entity, snapshot and Parquet checksum before reading, then offers
an explicit `errorifexists` Delta write. Join only on the publisher's stable `site_id`
within an explicit snapshot. Do not spatially infer a link to Water Bodies or EA data.
Power BI can consume the small snapshot GeoJSON as an Azure Maps reference layer;
status and retrieval time must remain visible. No Fabric SDK is added to WaterGeo.
