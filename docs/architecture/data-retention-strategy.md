# Data retention strategy

| Store/profile | Content | Retention rule |
| --- | --- | --- |
| PostGIS | current compatible operational snapshots, versioned reference entities, explicitly bounded retrievals | append-only snapshot metadata; keep operational rows bounded through an operator-reviewed retention window; never turn latest feeds into an unbounded event warehouse |
| Raw evidence | exact bounded publisher bytes, response metadata, checksums and validation manifest | durable before publication; rejected bytes remain inspectable and are never loaded; retention follows source/licence policy |
| Static publication | one immutable, self-describing accepted snapshot for browser use | replace by publication ID; retain only intentional releases/artifacts; show generation and source retrieval times |
| GeoParquet/Parquet | spatial entities and analytical facts with source/snapshot IDs | edition-oriented archive; partition large observations by source and reporting period |
| Future OneLake/Fabric | copies of governed analytical exports | downstream consumption only; WaterGeo evidence and acceptance remain authoritative |

Operational products use `CURRENT/LATEST`; recent series are explicitly bounded;
historical retrieval requires a declared scope; long analytical history belongs in
Parquet rather than indefinitely growing API tables. Expected national latest counts
are modest: roughly 1,000 rainfall gauges, several thousand flood areas, hundreds of
warnings during events, hundreds of bathing waters, and company-performance facts in
the low tens of thousands per publication—not unlimited telemetry histories.

