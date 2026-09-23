# Stream and water-company public source assessment

Reviewed 2026-09-23 using only public publisher pages and public ArcGIS REST
responses. WaterGeo UK is independent of Stream, Severn Trent Water and every other
publisher named here. Inclusion or assessment does not imply endorsement.

## Discovery method

[Ofwat's public open-data page](https://www.ofwat.gov.uk/regulated-companies/open-data-in-the-water-industry/)
identifies [Stream](https://www.streamwaterdata.co.uk/) as the sector platform.
Stream is an ArcGIS Hub backed by organisation `XxS6FebPX29TRGDJ`. Its public ArcGIS
catalogue contained 426 items: 207 Feature Services, 15 CSVs, two file geodatabases,
one WMS and supporting pages/documents. 214 catalogue records carried a CC BY 4.0
constraint. Licence metadata is item-specific, so a platform-wide count is not a
licence for records whose item metadata is absent or different.

Candidates were compared on documented licence, public unauthenticated access,
publisher identity, stable record identity, completeness, scale, geometry quality,
edition semantics and value beyond WaterGeo's national sources.

| Candidate | Public contract and licence | Coverage and identity | Measured suitability |
| --- | --- | --- | --- |
| Severn Trent Water raw-water reservoir levels 2025 | Public Stream Feature Service; item states CC BY 4.0 and credits Severn Trent Water; query-only, no account/key | 728 weekly rows: 14 reservoir IDs × 52 dates, 6 Jan–29 Dec 2025; point geometry; separate 2023/2024 catalogue editions are retained | **Selected.** Complete, small, clean, versioned company operational data with stable reservoir/date keys and useful locations. |
| Southern Water sewer catchment boundaries | Public Stream Feature Service; item states CC BY 4.0 and credits Southern Water | 376 unique `BoundaryId` values and names; 359 Polygon/17 MultiPolygon features | High geospatial value, but a 17,665,796-byte WGS84 export had 13 invalid geometries. Deferred for an explicit source-geometry assessment rather than generic repair. |
| Southern Water reservoir levels, 2002–present | Public Stream Feature Service; catalogue says CC BY 4.0 but the direct item licence text only says “CC BY” | 36,040 point readings; stable reservoir/date-shaped fields; monthly-update description | Valuable history, but larger and dynamically replaced, with inconsistent licence-version wording. Reconsider after publisher metadata is unambiguous. |
| South Staffs Water reservoir levels | Public Stream Feature Service; explicit CC BY 4.0 | 90 current rows at review time, one reservoir (`BLIT`) | Clean and automatable but too narrow for the first pattern when a comparable 14-reservoir edition is available. |
| National Storm Overflow Hub | Stream/Water UK public map; Water UK reports 14,187 English overflows and a third-party API | Near-real-time data is prepared and owned by nine respective companies; the Hub says each company is responsible for its dataset | Strong future value. The reviewed Hub page does not itself establish one immutable, licensed, stable unified download contract; company API/event semantics need a dedicated assessment. |
| Annual performance tables and domestic water quality | Many public Stream services, with mixed item-level licence completeness | Regulatory tables and company sample/result records | Not first choice: APR substantially duplicates regulated reporting, while water-quality semantics overlap Phase 3 and vary by company/edition. |
| South East Water portal | Official public CSV downloads; bespoke licence based on OGL v3, requiring “Incorporating South East Water Open Data under licence” | APR and distribution-input datasets; portal says new datasets are added over time | Legally reusable and worth revisiting, but the current catalogue is narrow and less geospatial than the selected source. |
| Thames Water API portal | Company documentation describes JSON/CSV APIs and a perpetual attribution licence | Includes storm-overflow/acoustic/APR data; some download flows use signed URLs and the portal has registered users | Deferred: authentication, signed-link stability and dataset-specific terms need a separate contract review before automation. |

Browser-only dashboards and undocumented endpoints were excluded. The Stream ArcGIS
REST service is a documented machine-readable public service, not an HTML scrape.

## Selected source contract

- Publisher: Severn Trent Water.
- Platform: Stream Water Data, hosted on ArcGIS Online.
- Item: `0bbd0dd0487346a893d4d615aad9d289`, “Severn Trent Water Raw Water Storage - Reservoir Levels 2025”.
- Public item URL: `https://www.streamwaterdata.co.uk/datasets/0bbd0dd0487346a893d4d615aad9d289`.
- Feature Service: `https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/Severn_Trent_Water_Raw_Water_Storage_-_Reservoir_Levels_2025/FeatureServer/0`.
- Access: public, query-only, no login or API key.
- Licence: Creative Commons Attribution 4.0, as stated in the item's licence metadata.
- Attribution used by WaterGeo: “Severn Trent Water Raw Water Storage - Reservoir Levels 2025 © Severn Trent Water, licensed under CC BY 4.0.”
- Edition: calendar year 2025. The source is a dated edition; separate 2023 and 2024 items remain discoverable.
- Service CRS: Web Mercator, EPSG:3857 (`wkid` 102100, `latestWkid` 3857).
- Accepted export: the publisher's ArcGIS query service returns point GeoJSON with explicit `outSR=4326`. Raw responses and the native layer definition are both retained, so the service-side presentation CRS is explicit.
- Stable entity identity: publisher `RESERVOIR_ID`.
- Stable reading identity: (`RESERVOIR_ID`, exact publisher `DATE` timestamp). ArcGIS `FID` is retained for evidence checking but is not exposed as the domain identity.
- Values: source capacity and current level are strings with `ML` units; percentage is numeric. WaterGeo parses finite numbers without conversion and retains exact source fields.

The source warns that levels must not determine hosepipe-ban or other supply measures,
that seasonal high/low values may be normal, that capacity definitions can differ
between companies, and that the data does not replace safety checks. WaterGeo must
surface these caveats and must not infer water-supply risk.

## Live contract verification

The direct layer reported `maxRecordCount=2000`, query capability, point geometry and
the reviewed field schema. A complete ordered GeoJSON probe returned:

- 728 records and 14 reservoirs, exactly 52 dates per reservoir;
- 728 unique (`RESERVOIR_ID`, `DATE`) keys;
- publisher timestamps from 2025-01-06T00:00:00Z through 2025-12-29T00:00:00Z;
- 728 valid, non-empty WGS84 points;
- no nulls in any accepted field;
- `ML` for every capacity and current-level unit;
- percentage range 19.9–100;
- 271,267 response bytes;
- response SHA-256 `d21158ca1e9bd282a5b96f0f1aa987dc1c70d471e020b750756f48e0e6c4e9a5`.

This probe hash describes that one review request. Production evidence uses bounded
publisher-ID pages and hashes every exact response, so its content hash is intentionally
different. ArcGIS returns GeoJSON with `application/json`, an ETag, Last-Modified and
request-unit headers. Only stable, useful response headers are retained.

The production client then completed and independently re-read evidence at
`data/raw/stream/severn-trent-reservoir-levels/7736943b-4c53-474e-91dc-2c1d5ea282b4`
(ignored by Git): eight responses totaling 306,012 bytes, 14 reservoirs and 728
readings. Content SHA-256 is
`c7bfb3d7fed454fcc802dda0ff4426618b8b830cb84e238febd5e75990e030c7`;
normalized SHA-256 is
`3b89b1b593d6ff6f8e0aef5a671318dd3dedc3bdb07182edf8665601a8c2e0f6`.
The item creation/modification milliseconds were `1779029424000` and `1779030284000`.

The layer declares `DATE` as `esriFieldTypeDate` with UTC time reference, but records
during British Summer Time are encoded at 23:00 UTC on the preceding calendar day
(for example the nominal weekly transition after 24 March is `2025-03-30T23:00:00Z`).
The service does not document a local-date interpretation. WaterGeo therefore preserves
the exact aware UTC timestamp and does not silently add a day or label it local midnight.

## Accepted implementation scope

Retrieve immutable item metadata, layer schema, object-ID sets and bounded GeoJSON
pages from fixed HTTPS hosts/paths. Compare object IDs and item modification metadata
before and after paging, reject duplicates/schema changes/redirects and cap requests,
records, pages, bytes, retries and time. A matching ID set cannot prove a publisher-
atomic snapshot if values change without item metadata changing; the manifest therefore
describes a retrieval, not a transactional publisher edition.

Normalize the 2025 edition only. Preserve exact publisher identifiers, timestamps, names,
locations, capacity, current level, percentage, units and raw properties. Do not merge
other companies/years, calculate risk, interpolate gaps, convert units, relate points to
Ofwat/EA datasets or treat a reservoir point as its physical polygon. Later different
evidence coexists; an exact retry must verify stored child rows.
