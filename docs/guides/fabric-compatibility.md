# Fabric compatibility: optional file consumption

WaterGeo can run without Microsoft Fabric. These instructions describe a consumer
workflow in a user's existing Fabric environment; nothing here provisions or
authenticates from WaterGeo. Tenant capacity, preview availability and permissions
must be checked by that user. No Fabric deployment has been tested in this phase.

## Entity mapping

| WaterGeo entity | Implemented output | Consumer use |
| --- | --- | --- |
| Reviewed water-supply area | GeoJSON Feature; GeoParquet WKB row | Exact feature inspection; notebook analysis |
| Water-supply overview | PMTiles/MVT `water_supply` layer | Fabric Map or WaterGeo overview |
| Export dataset/provenance | JSON manifest; Parquet schema metadata and row fields | Snapshot identification, hashes, licensing |
| Hydrology, Water Quality, reservoirs, Water Bodies | Existing bounded API and SDK | Future dedicated exports; no new file exporter claimed |

Stable row identity is `(snapshot_id, source_id)`; IDs are strings in Parquet to
avoid consumer numeric coercion. `properties_json` and `presentation_json` preserve
source notices and reviewed transformation metadata. Geometry is binary WKB, not a
Delta spatial type. A Spark write can make a Delta table while retaining this binary
column, but it does not automatically retain GeoParquet schema metadata: keep the
manifest alongside it and preserve provenance columns.

## Lakehouse / OneLake example

1. Generate and verify a bundle as described in [exports](phase-8-exports.md).
2. In an existing Lakehouse, upload the entire directory under
   `Files/watergeo/water-supply/<snapshot>/`. Preserve filenames and manifest.
3. Use the [notebook example](../../examples/fabric/lakehouse_consumer.py) with a
   default Lakehouse attached. It checks the Parquet hash before reading. Its optional
   table-writing function uses `errorifexists`, so it cannot overwrite a table.
4. Retain one table or partition per snapshot and an explicit accepted snapshot
   selection. Do not append indistinguishable editions into one table.

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
