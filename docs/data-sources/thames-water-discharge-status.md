# Thames Water discharge-status semantics

Source: `https://api.thameswater.co.uk/opendata/v2/discharge/status`. The reviewed
contract is API v2.0.1, normalization `thames-water-discharge-status-v2.0.1-v1`.

Each refresh stores the exact response and a checksummed manifest before validation.
Publication is append-only and atomic. An identical source body resolves to the
existing snapshot after verifying every stored child row. A changed API version,
metadata shape, field set, status vocabulary, duplicate/invalid ID, malformed BNG
coordinate or invalid timestamp fails closed.

The stable row key is `(snapshot_id, site_id)`, where the publisher's `uniqueId`
matches `TWL[0-9]{5}`. Source coordinates are EPSG:27700 and PostGIS transforms them
to exact API presentation points in EPSG:4326. WaterGeo preserves permit number,
grid reference, receiving watercourse, status, the publisher's past-48-hours flag,
and most recent indicated start/stop values.

The API's timestamps do not include an offset. They are stored as PostgreSQL
`timestamp without time zone` and serialized without adding `Z` or an offset.
WaterGeo does not claim they are UTC. `Discharging`, `Not discharging` and `Offline`
are publisher monitor states. They do not establish discharge volume, water quality,
bathing safety, environmental harm or a relationship to another dataset.

Retrieval is fixed to one HTTPS host, refuses redirects, disables environment proxy
inheritance, limits responses to 2 MiB, retries only a small status-code set and caps
records at 1,000. Tests use synthetic source-shaped fixtures and never call Thames
Water.
