# Data refresh policy

WaterGeo separates a publisher’s update behaviour, an operator retrieval policy, and a
static publication cadence. A measurement interval is not a retrieval guarantee.

| Product | Class | Publisher semantics | Configured retrieval | Static preview / publication |
| --- | --- | --- | --- | --- |
| Water supply | STATIC VERSIONED | dated release | manual new-version acceptance | gated daily preview reuses accepted release |
| Hydrology latest | DYNAMIC LATEST | measurements often 15-minute; transfers vary | hourly at :17 UTC, opt-in gate | gated daily preview replays accepted evidence |
| Hydrology history | BOUNDED ON-DEMAND | recent/history API | explicit request only | selected accepted retrievals only |
| Catchments | STATIC VERSIONED | river-basin plan edition | manual | gated daily preview reuses accepted edition |
| Water Quality metadata | DYNAMIC LATEST | publisher metadata changes | daily 02:43 UTC, opt-in gate | gated daily preview replays accepted evidence |
| Water Quality observations | BOUNDED ON-DEMAND | observation archive | explicit bounded request only | selected accepted retrievals only |
| Reservoir levels | STATIC VERSIONED | dated Stream edition | manual | gated daily preview reuses accepted edition |
| Thames discharge | DYNAMIC LATEST | operational publisher indications | :07/:22/:37/:52 UTC, opt-in gate | gated daily preview replays accepted evidence |
| Rainfall | DYNAMIC LATEST | 15-minute accumulation; transfers typically once/twice daily and may increase | hourly at :27 UTC, opt-in gate | gated daily preview replays accepted evidence |
| Flood warnings | DYNAMIC LATEST | feed updated about every 15 minutes | :02/:17/:32/:47 UTC, opt-in gate | gated daily preview; visibly dated and never emergency advice |
| Bathing waters | SEASONAL | sampling May–September; annual classifications and publisher advice | weekly in season, monthly outside it, opt-in gate | gated daily preview reuses latest accepted retrieval |
| Company performance | ANNUAL/PERIODIC | named Ofwat publications/versions | manual when a new official edition is accepted | gated daily preview reuses accepted edition |

Hosted operational schedules are disabled unless their exact enable variable is set.
The daily static preview replays pinned evidence behind a separate gate; public
Pages deployment is manually triggered and has no promised daily cadence. The repository does
not currently operate a persistent hosted database, and no schedule implies a public
freshness SLA.

High-volume histories never run as national schedules. They remain bounded retrievals
or analytical archives with explicit provenance.


See [refresh and publication](refresh-and-publication.md) for current commands,
workflow gates and the separately proposed automation path.
