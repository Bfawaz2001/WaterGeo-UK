# Phase 12 local v1 rehearsal measurements

Measured 27 September 2026 on the maintainer's Apple Silicon development machine.
These results describe one local run and are not production capacity claims.

## Complete demo

The starting database was already migrated to `0011` and held only Water Quality:
one accepted snapshot and 66,300 sampling points. Offline bootstrap reused that row
and loaded retained source bundles for Water Supply, Hydrology, Catchments, Severn
Trent and Thames. Final source status reported all six explorer sources available.
The complete HTTP smoke passed health, readiness, source status, unified search and
one representative query for each source.

## Built explorer

The production Vite build emitted 0.50 kB HTML, 12.02 kB main CSS, 267.69 kB main
JavaScript and a demand-loaded 1,050.79 kB MapLibre chunk (uncompressed sizes). The
MapLibre chunk remains the known dominant frontend cost; Phase 12 metadata/status UI
did not add a new package. The same-origin nginx rehearsal passed explorer fallback,
API routing and readiness. HTML used `no-cache`; hashed assets used one-year immutable
caching.

## Backup and restore

The source and target were separate disposable PostgreSQL/PostGIS containers. The
source was seeded by a read-only logical copy of the complete local demo database.

| Measurement | Result |
| --- | ---: |
| Custom-format backup bytes | 68,025,634 |
| Backup wall time | 10 s |
| Restore wall time | 10 s |
| Restored Alembic revision | 0011 |
| Accepted snapshot rows in signature | 6 |

The pre/post snapshot signature was identical:
`6:376b0d7817315368a607cdb9d999654d`. A separately started read-only API against the
restored database passed all ten complete-demo smoke checks. The normal development
database was read only during seeding and was never a restore target.
