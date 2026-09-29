# ADR 0015: National products and static publication

Status: accepted for Phase 15

## Decision

Rainfall, flood monitoring, bathing waters and company performance are separate append-only governed source products. Exact raw responses and retrieval metadata precede normalization. Accepted snapshots serve the hosted API, the deterministic static publication and optional analytical exports; those consumption profiles do not retrieve publishers independently.

Operational datasets retain latest accepted bounded snapshots in PostGIS. Unlimited telemetry history remains outside the default model. The static explorer reads same-origin immutable assets through the same frontend API boundary and explicitly disables server-only point-in-polygon lookup. Static publication fails closed on missing provenance, snapshot changes or unsafe overwrite.

Company-boundary attachment uses only a versioned reviewed crosswalk. Flood severity and bathing-water facts retain publisher terminology and prominent safety caveats.

## Consequences

The zero-cost profile is useful without a running API or database, but it is a dated snapshot. Hosted and static cadences differ. Static geometry assets can be larger than some free-host limits, so large national layers must be tiled or split before deployment. No deployment is activated by this ADR.
