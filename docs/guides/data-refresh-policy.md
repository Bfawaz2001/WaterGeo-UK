# Data refresh policy

WaterGeo separates a publisher’s update behaviour, a hosted retrieval policy, and a
static publication cadence. A measurement interval is not a retrieval guarantee.

| Product | Class | Publisher semantics | Hosted retrieval | Static publication |
| --- | --- | --- | --- | --- |
| Water supply | STATIC VERSIONED | dated release | manual new-version acceptance | daily bundle reuses accepted release |
| Hydrology latest | DYNAMIC LATEST | measurements often 15-minute; transfers vary | hourly at :17 UTC, opt-in gate | daily accepted snapshot |
| Hydrology history | BOUNDED ON-DEMAND | recent/history API | explicit request only | selected accepted retrievals only |
| Catchments | STATIC VERSIONED | river-basin plan edition | manual | daily bundle reuses accepted edition |
| Water Quality metadata | DYNAMIC LATEST | publisher metadata changes | daily 02:43 UTC, opt-in gate | daily accepted snapshot |
| Water Quality observations | BOUNDED ON-DEMAND | observation archive | explicit bounded request only | selected accepted retrievals only |
| Reservoir levels | STATIC VERSIONED | dated Stream edition | manual | daily bundle reuses accepted edition |
| Thames discharge | DYNAMIC LATEST | operational publisher indications | :07/:22/:37/:52 UTC, opt-in gate | daily accepted snapshot |
| Rainfall | DYNAMIC LATEST | 15-minute accumulation; transfers typically once/twice daily and may increase | hourly at :27 UTC, opt-in gate | daily accepted snapshot |
| Flood warnings | DYNAMIC LATEST | feed updated about every 15 minutes | :02/:17/:32/:47 UTC, opt-in gate | daily snapshot; visibly dated and never emergency advice |
| Bathing waters | SEASONAL | sampling May–September; annual classifications and publisher advice | weekly in season, monthly outside it, opt-in gate | daily bundle reuses latest accepted retrieval |
| Company performance | ANNUAL/PERIODIC | named Ofwat publications/versions | manual when a new official edition is accepted | daily bundle reuses accepted edition |

Hosted operational schedules are disabled unless their exact enable variable is set.
Static publication is a daily snapshot job with a separate gate. The repository does
not currently operate a persistent hosted database, and no schedule implies a public
freshness SLA.

High-volume histories never run as national schedules. They remain bounded retrievals
or analytical archives with explicit provenance.

