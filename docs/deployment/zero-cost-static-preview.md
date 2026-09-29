# Zero-cost static preview

**Status: repository capability only; no public site or provider project exists.**

The publication path is accepted evidence → ephemeral PostGIS → deterministic
`watergeo-static-publish` bundle → the same explorer built in static mode → immutable
artifact. The bundle is vendor-neutral files and requires no API, database, secrets or
browser CORS exception at runtime.

## Recommendation and verified limits

Use GitHub Pages first because this is a public repository and standard GitHub-hosted
Actions are free for public repositories. Current official limits state a 1 GB maximum
published site, 100 GB/month soft bandwidth, and a 10-minute Pages deployment timeout.
The artifact workflow reports file sizes; an operator must verify the final site remains
inside those limits before enabling Pages.

Cloudflare Pages remains a fallback, but its Free plan currently limits one asset to
25 MiB, a site to 20,000 files, 500 builds/month and one concurrent build. WaterGeo’s
measured national water-supply GeoJSON was about 50.8 MB, so it cannot be published as
one Cloudflare Pages asset. PMTiles or chunked GeoJSON must keep every file below the
limit. Static asset requests do not invoke Functions and are described as free and
unlimited, but no Cloudflare account is provisioned here.

## Workflow and refresh

The inactive-by-default workflow downloads a manually prepared, checksum-pinned
`watergeo-accepted-evidence` Actions artifact, safely extracts it, replays every required
product into disposable PostGIS, validates source contracts, publishes data, builds
with `VITE_WATERGEO_DATA_MODE=static`, runs browser acceptance tests and uploads an
immutable artifact. It does not fetch publisher data independently. This manual evidence
step remains required until the project has a suitable free durable evidence store.
Scheduled publication is separately gated and should run daily. Enabling
GitHub Pages and its environment remains a manual repository setting and is not done
by this phase.

Static mode provides bounded browser filtering over the published snapshot. It cannot
reproduce server-side history retrieval, arbitrary national database queries or live
refresh. Those controls are disabled or labelled. Every view shows publication and
source retrieval time. Migrating to the Phase 14 profile changes the frontend mode to
`api` and supplies the same governed products through FastAPI/PostGIS.
