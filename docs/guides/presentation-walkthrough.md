# WaterGeo UK — Project Presentation & Technical Walkthrough

[Back to the project overview](../../README.md)

This guide supports a 10–15 minute technical demonstration of the implemented
WaterGeo UK platform. The [public explorer](https://bfawaz2001.github.io/WaterGeo-UK/)
is a governed static edition. The local path runs React → FastAPI → PostgreSQL/PostGIS
and can contain a newer accepted snapshot. Neither path is a live publisher feed.

## Pre-meeting setup

Run these checks from the repository root. They preserve existing database volumes.

1. Confirm Docker Desktop and Compose are usable, then start PostGIS:

   ```bash
   docker version
   docker compose version
   docker compose up --build --wait db
   ```

2. Check whether an API is already listening and whether it is ready:

   ```bash
   lsof -nP -iTCP:8000 -sTCP:LISTEN
   curl -fsS http://127.0.0.1:8000/ready
   ```

   A listener may be the WaterGeo API, so inspect it rather than killing an arbitrary
   process. If nothing responds, start the API in terminal 1:

   ```bash
   uv run --locked uvicorn watergeo.api.app:create_app --factory --reload --no-access-log --no-proxy-headers
   ```

3. In terminal 2, confirm the accepted product state:

   ```bash
   curl -fsS http://127.0.0.1:8000/ready
   curl -fsS http://127.0.0.1:8000/v1/sources/status
   ```

   Read the returned retrieval/version fields before describing freshness. A source
   can be available from its previous accepted snapshot after a rejected refresh.

4. Start the explorer in terminal 3:

   ```bash
   cd web
   npm ci
   npm run dev
   ```

   Open the Vite URL printed in the terminal, normally <http://127.0.0.1:5173/>.
   Keep the [public static explorer](https://bfawaz2001.github.io/WaterGeo-UK/) in a
   second tab as a fallback. A copied localhost link works only on this computer;
   the public static edition may have an older accepted snapshot.

## 10–15 minute presentation plan

### Part 1 — Introduction (1 minute)

- **Objective:** explain the problem and the implemented product.
- **Say:** “Public water information is split across publishers, schemas, spatial
  models and time semantics. WaterGeo retains those differences while making the
  accepted products searchable in one geospatial explorer.”
- **Open:** the [README](../../README.md), then the public or local explorer.
- **Show:** the ten-product portfolio and the distinction between the public static
  explorer and the local API/database stack.
- **Caveat:** WaterGeo is independent and does not certify publisher data as current.

### Part 2 — Explorer demonstration (4 minutes)

- **Objective:** demonstrate discovery, selection, filters and provenance.
- **Say:** “The map begins broad, then uses bounded nearby queries and exact selected
  geometry. The detail panel carries source, licence, snapshot and time context.”
- **Open/click:**
  1. Search for **Fornalls Bridge** and open its Hydrology detail. Point out the
     measurement unit/period and observation time versus retrieval time.
  2. Enable Bathing waters, search for **West Kirby**, and show that `Sufficient` is
     an annual publisher classification in the tested local snapshot. Filter counts
     describe loaded nearby results, not a national total.
  3. Search **Anglian Water**. Explain that each result is an exact publisher-defined
     April 2024 area. Returned matches are not asserted to be the company's complete
     inventory. Open one area and separate its geometry from company-wide performance.
  4. Open **Rivers & Catchments**, find **Till from Source to Linhope Burn**, and
     select it. The map fits once to its multipart publisher geometry and remains
     manually navigable.
  5. Use **Copy view** and show its confirmation. Explain that supported map/filter/
     selection state is encoded, while API responses, secrets and device location are not.
- **Read alongside:** [explorer interpretation](explorer-data-interpretation.md) and
  [navigation design](../design/explorer-navigation.md).
- **Caveat:** show rainfall only with its accepted-snapshot context. The 11 October
  refresh was rejected because one publisher value was a list rather than a scalar;
  the 30 September accepted snapshot remained available.

### Part 3 — Architecture (3 minutes)

- **Objective:** connect the UI to the governed platform.
- **Say:** “Python retrieves bounded source evidence; source-specific validation
  creates accepted snapshots in PostgreSQL/PostGIS; FastAPI exposes read-only,
  snapshot-aware queries; React/TypeScript and MapLibre provide the explorer.”
- **Open:** [system overview](../architecture/system-overview.md), then
  [data flow](../architecture/data-flow.md).
- **Show:** the separate static publication path through GitHub Actions to GitHub
  Pages. Mention reviewed GeoJSON/PMTiles/GeoParquet exports and optional Fabric
  interoperability as consumption paths, not a deployed Fabric environment.
- **Caveat:** GitHub Pages serves immutable files; it does not host FastAPI or PostGIS.

### Part 4 — Data reliability and governance (2 minutes)

- **Objective:** explain why an accepted item is traceable and why failure is safe.
- **Say:** “WaterGeo preserves raw response evidence, checksums, publisher identity,
  licence and retrieval metadata before normalization. Validation is source-specific,
  and atomic publication retains the last accepted snapshot if a refresh fails.”
- **Open:** [ingestion and evidence](../architecture/ingestion-and-evidence.md) and
  the [rainfall source contract](../data-sources/environment-agency-rainfall.md).
- **Show:** the rainfall rejection as evidence of validation working, plus the
  separately reviewed water-supply canonical and presentation transformations.
- **Caveat:** recent retrieval does not prove a recent publisher observation; rejected
  evidence is inspectable but is never loaded as accepted data.

### Part 5 — Roadmap and discussion (3–5 minutes)

- **Objective:** distinguish current capability from the next architecture decisions.
- **Open:** the [roadmap](../project/roadmap.md).
- **Say:** “Phase 18B governs historical rainfall and presents existing bounded
  Hydrology/Water Quality observations without combining incompatible measures.
  Phase 18C designs a complete, lightweight national point overview with explicit
  completeness metadata. Public API hosting and publication automation remain
  separate operational decisions.”
- **Discuss:** API/export/Fabric consumption, data governance guarantees and which
  user questions should guide the next product investment.
- **Caveat:** the roadmap is a review plan, not a publisher SLA or deployment promise.

## Discussion prompts

- Which water-data exploration problem would be most useful to solve next?
- Would historical trends and measure-safe comparisons add more value than more layers?
- Which evidence, provenance and freshness guarantees matter most to your decisions?
- Would governed exports, API access or Fabric/Power BI compatibility be useful?
- What would make the explorer clearer for a non-technical user?

## Likely questions

**Is this live?**  
No. Dynamic products are the latest WaterGeo-accepted retrieval in the environment;
the public site is an immutable static publication. Publisher observation time,
WaterGeo retrieval time and WaterGeo publication time are separate.

**How frequently does data update?**  
Each source has a reviewed cadence or version process. Workflow schedules are opt-in
and do not prove that a run succeeded. The public site changes only after a separately
validated and manually dispatched Pages publication.

**Where does the data come from, and are these official APIs?**  
The portfolio uses public Environment Agency, Ofwat/Commons Library, Thames Water and
Severn Trent via Stream sources. Some are official APIs; others are reviewed files or
linked-data endpoints. The [portfolio](../data-sources/source-portfolio.md) records
the specific route, licence and semantics.

**Why are not all rainfall stations named?**  
The accepted feed can withhold names and reduces coordinates. WaterGeo uses the exact
gauge identity as a safe fallback. An official station page confirms some names, but
a governed identity crosswalk with evidence and licence handling is required before
those names can replace the canonical fallback.

**What happens if a publisher API changes?**  
Unexpected schema, licence, identity or value shapes fail validation. Evidence is
retained for diagnosis and the previous accepted snapshot remains published.

**Does it contain historical measurements?**  
It supports bounded Hydrology history and separately bounded Water Quality
observations, but the explorer does not claim a complete historical archive. Rainfall
history and a chart-driven analytical experience are Phase 18B work.

**Why use PostGIS?**  
It provides indexed spatial containment, distance and geometry operations close to
the accepted data, while explicit CRS and snapshot contracts keep results reproducible.

**How is this different from publisher websites?**  
WaterGeo provides one governed discovery and software interface across independent
sources while retaining their identifiers, licences and caveats. It does not replace
publishers' official or safety services.

**Can it integrate with Microsoft Fabric?**  
Yes, through optional reviewed Parquet/GeoParquet and Lakehouse consumption examples.
Core WaterGeo has no Fabric runtime dependency and no Fabric deployment is claimed.

**Is the public API hosted?**  
No. The public deployment is static GitHub Pages. FastAPI/PostGIS runs locally or in
an operator-controlled environment.

**What does it cost to run?**  
The current public static site uses GitHub Pages. No measured end-to-end production
cost or SLA is claimed; a hosted database/API would need an explicit budget and review.

**Is this an official Ofwat or Environment Agency platform?**  
No. It is an independent personal open-source project and is not endorsed by a
publisher, water company or employer.

## Demonstration fallback plan

| Problem | Safe response |
| --- | --- |
| Port 8000 is occupied | Inspect the listener and `/ready`; use the existing WaterGeo process if healthy. Do not kill an unknown process. |
| PostgreSQL is unavailable | Show the public static explorer and the evidence/data-flow docs; do not delete volumes. |
| Public site has an older edition | State its publication ID/time, then use local mode for newer accepted data. |
| Rainfall remains stale | Show the last accepted snapshot and explain the retained rejection; do not call it current. |
| Basemap tiles fail | Use search, controls and detail panels over WaterGeo's visible fallback; explain the external tile dependency. |
| One source is unavailable | Use `/v1/sources/status`, name the unavailable product, and demonstrate another accepted source. |
| No nearby points appear | Search a named example or choose a region, then zoom; nearby results are bounded around the map centre. |
| Company overview seems incomplete | Demonstrate returned exact areas individually and state that no complete company-wide geometry contract is claimed. |
| Water Body geometry is unavailable | Show its metadata and visible error, then use another Water Body; no arbitrary map target is invented. |
| Screen is narrow | Collapse Layers & filters, use search, and keep the detail panel visible; avoid relying on hover. |

Before presenting real values, repeat the source-status check and verify the named
examples in the current environment. Never substitute synthetic test fixtures for
accepted public evidence without labelling them explicitly.
