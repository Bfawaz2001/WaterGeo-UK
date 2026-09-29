# Zero-cost public static beta

**Status: launch-ready repository capability. GitHub Pages is not enabled and no
public WaterGeo URL exists.**

WaterGeo can build a repository-subpath-safe static explorer for
`/WaterGeo-UK/`. Browser runtime needs only immutable files; it does not need FastAPI,
PostGIS, credentials, CORS exceptions, or a publisher connection.

## Build contract

The manual `.github/workflows/static-pages.yml` workflow performs:

1. checksum-pin and safely extract operator-reviewed accepted evidence;
2. replay every required source into disposable PostGIS;
3. start the local read-only API and run `watergeo-static-publish --analytics`;
4. build the explorer with `VITE_BASE_PATH=/WaterGeo-UK/` and static data beneath
   `/WaterGeo-UK/watergeo-data/`;
5. run unit and Pages-style browser acceptance;
6. create `404.html` for GitHub Pages SPA fallback;
7. reject private/runtime material with
   `python -m watergeo.operations.public_artifact web/dist`;
8. upload the dedicated Pages artifact, then use the protected `github-pages`
   deployment environment.

The workflow is `workflow_dispatch` only, restricted to this repository's `main`
branch, and has no schedule. Its build job is read-only; only the deploy job receives
`pages: write` and `id-token: write`. The existing Phase 15 preview workflow remains an
artifact-only scheduled/manual validation and now runs the same public-artifact guard.

## Publication report and limits

Each data bundle includes `publication-report.json` with the publication identity and
time, WaterGeo commit/version, total bytes/files, product and analytical sizes/counts,
largest assets, and a 1 GiB GitHub Pages site-limit assessment. Canonical hashes remain
in `manifest.json`; the report links to that map rather than copying it.

Reject a release if the report exceeds the Pages site limit, required provenance or
licensing is missing, hashes fail, a required asset returns 404, the Pages base-path
test fails, the artifact guard fails, or static browser acceptance fails.

## Activate after review

1. Review this branch and merge it to `main`.
2. In repository **Settings → Pages**, select **GitHub Actions** as the source. Do not
   add a custom domain yet.
3. Configure the protected `static-preview-build` and `github-pages` environments and
   the checksum-pinned `WATERGEO_STATIC_EVIDENCE_RUN_ID` and
   `WATERGEO_STATIC_EVIDENCE_SHA256` repository variables.
4. Manually dispatch **Publish governed static beta to GitHub Pages** from `main`.
5. Inspect `watergeo-data/publication-report.json`, the artifact-guard output and the
   browser-acceptance result before approving the `github-pages` deployment.
6. Verify `https://bfawaz2001.github.io/WaterGeo-UK/`, its data assets, search, map
   interaction, provenance, and the independence statement.

## Rollback

Retain the known-good workflow run and immutable publication ID. Redeploy that prior
Pages artifact through the protected environment. Never replace files while claiming
the prior publication identity; a changed governed input must produce a new identity.

## Product semantics

The banner's publication time comes from `manifest.generated_at`. Publisher
observation/publication time and WaterGeo retrieval time remain separate. Operational
layers are latest accepted publisher snapshots, not live feeds. Static mode offers
bounded filtering and explicitly marks API-only drill-downs. WaterGeo is an independent
open-source project and is not endorsed by Ofwat, the Environment Agency, or a water
company.

No complete real multi-source artifact has been published. The official Ofwat workbook
still needs the documented operator review and preparation step.
