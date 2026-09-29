# Zero-cost public static beta

**Status: launch capability and evidence packaging are implemented. The official WCPR
2024–25 workbook remains an external manual-download blocker, so no complete real
candidate exists. GitHub Pages is not enabled and no public WaterGeo URL exists.**

WaterGeo can build a repository-subpath-safe static explorer for
`/WaterGeo-UK/`. Browser runtime needs only immutable files; it does not need FastAPI,
PostGIS, credentials, CORS exceptions, or a publisher connection.

## Build contract

The operator first builds `accepted-evidence.tar.gz` with
`watergeo-static-evidence-package`. The command requires each of these validated source
directories exactly once:

`ofwat`, `hydrology`, `catchments`, `water-quality`,
`stream-reservoir-levels`, `thames-discharge-status`, `rainfall`,
`flood-monitoring`, `bathing-waters`, and `company-performance`.

Each source is validated with its normal WaterGeo reader. The command rejects missing,
duplicate or unknown sources, symlinks, changed checksums and unsafe output overwrite.
It writes deterministic `replay.json` and `evidence-package.json` members, records the
WaterGeo commit/version and per-source bytes, file counts and SHA-256, then prints the
archive SHA-256 and byte count. For example:

```bash
uv run --locked watergeo-static-evidence-package \
  --source ofwat=/ABSOLUTE/validated/ofwat \
  --source hydrology=/ABSOLUTE/validated/hydrology \
  --source catchments=/ABSOLUTE/validated/catchments \
  --source water-quality=/ABSOLUTE/validated/water-quality \
  --source stream-reservoir-levels=/ABSOLUTE/validated/reservoirs \
  --source thames-discharge-status=/ABSOLUTE/validated/thames \
  --source rainfall=/ABSOLUTE/validated/rainfall \
  --source flood-monitoring=/ABSOLUTE/validated/flood \
  --source bathing-waters=/ABSOLUTE/validated/bathing \
  --source company-performance=/ABSOLUTE/validated/company-performance \
  --output /ABSOLUTE/launch/accepted-evidence.tar.gz
```

Keep the archive outside Git. The extractor independently rejects unsafe members and
recomputes the replay and source hashes. Replay then invokes every normal source reader
again before database publication.

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

## Private evidence handoff

Upload the archive as the single `accepted-evidence.tar.gz` asset on a GitHub **draft
release**. Draft assets are limited to collaborators with push access and each release
asset must be under 2 GiB; WaterGeo applies a stricter 1 GiB archive cap. GitHub's
documented release API exposes draft releases only to identities with push access, so
the ordinary workflow `GITHUB_TOKEN` is not assumed to work. Store a fine-grained token
belonging to an operator with repository push access as the protected
`static-preview-build` environment secret `WATERGEO_STATIC_EVIDENCE_TOKEN`, limited to
this repository and **Contents: read**.

Both workflows require `WATERGEO_STATIC_EVIDENCE_RELEASE_ID` and
`WATERGEO_STATIC_EVIDENCE_SHA256`. They require the configured release to remain a
draft, require exactly one uploaded asset with the expected name, check GitHub's asset
digest when present, download by asset ID, verify the pinned SHA-256, safely extract,
and validate the package again. A draft asset is mutable, but any replacement fails the
checksum pin. The earlier workflow-run artifact handoff has been removed so there is
one production path.

## Publication report and limits

Each data bundle includes `publication-report.json` with the publication identity and
time, WaterGeo commit/version, total bytes/files, product and analytical sizes/counts,
largest assets, and a preliminary 1 GiB limit assessment scoped explicitly to the data
bundle. Canonical hashes remain in `manifest.json`; the report links to that map rather
than copying it. The data-only result does not prove that the complete site fits the
Pages limit. The final `python -m watergeo.operations.public_artifact web/dist` check,
after HTML, JavaScript, CSS, icons and data have been assembled, is authoritative for
complete-site size.

Reject a release if the data bundle exceeds the preliminary limit, required provenance
or licensing is missing, hashes fail, a required asset returns 404, the Pages base-path
test fails, the final-site artifact guard fails, or static browser acceptance fails.

## Post-merge activation

Do this only after all ten real evidence sources, including the reviewed official WCPR
edition, produce a complete local candidate with no synthetic data.

```bash
OWNER_REPO=Bfawaz2001/WaterGeo-UK
EVIDENCE_TAG=watergeo-evidence-YYYYMMDD
ARCHIVE=/ABSOLUTE/launch/accepted-evidence.tar.gz
EVIDENCE_SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"

gh release create "$EVIDENCE_TAG" "$ARCHIVE" \
  --repo "$OWNER_REPO" --target main --draft \
  --title "Reviewed WaterGeo static evidence YYYY-MM-DD" \
  --notes "Operator-reviewed input for the pinned static publication workflow."
EVIDENCE_RELEASE_ID="$(gh release view "$EVIDENCE_TAG" --repo "$OWNER_REPO" \
  --json databaseId --jq .databaseId)"
gh variable set WATERGEO_STATIC_EVIDENCE_RELEASE_ID --repo "$OWNER_REPO" \
  --body "$EVIDENCE_RELEASE_ID"
gh variable set WATERGEO_STATIC_EVIDENCE_SHA256 --repo "$OWNER_REPO" \
  --body "$EVIDENCE_SHA256"
```

Create a fine-grained token for the operator identity, scoped only to this repository
with Contents read, then store it without echoing it:

```bash
gh secret set WATERGEO_STATIC_EVIDENCE_TOKEN --repo Bfawaz2001/WaterGeo-UK \
  --env static-preview-build
```

Configure the protected `static-preview-build` and `github-pages` environments. In
**Settings → Pages**, select **GitHub Actions** as the source and do not add a custom
domain. Then run and inspect the preview before publishing:

```bash
gh workflow run static-preview-build.yml --repo Bfawaz2001/WaterGeo-UK --ref main
gh run list --repo Bfawaz2001/WaterGeo-UK --workflow static-preview-build.yml --limit 1
# Inspect the artifact, publication report, counts, provenance and browser result.
gh workflow run static-pages.yml --repo Bfawaz2001/WaterGeo-UK --ref main
gh run list --repo Bfawaz2001/WaterGeo-UK --workflow static-pages.yml --limit 1
curl -fsS https://bfawaz2001.github.io/WaterGeo-UK/watergeo-data/manifest.json
```

Approve the `github-pages` environment deployment in GitHub if required, then verify
the explorer, all four required top-level JSON assets, real search/detail paths, source
status, provenance, mobile layout, absence of `/v1` calls and absence of root-level
`/watergeo-data` calls.

## Rollback

For every approved deployment record its publication ID, WaterGeo commit, evidence
release ID, archive SHA-256, preview run ID and Pages run/deployment ID. Retain prior
draft evidence releases. To restore the previous data publication, repin the known-good
release and checksum and dispatch the Pages workflow:

```bash
gh variable set WATERGEO_STATIC_EVIDENCE_RELEASE_ID --repo Bfawaz2001/WaterGeo-UK \
  --body PREVIOUS_RELEASE_ID
gh variable set WATERGEO_STATIC_EVIDENCE_SHA256 --repo Bfawaz2001/WaterGeo-UK \
  --body PREVIOUS_ARCHIVE_SHA256
gh workflow run static-pages.yml --repo Bfawaz2001/WaterGeo-UK --ref main
```

If application code also changed, restore the recorded WaterGeo commit through a normal
reviewed revert PR before dispatching. Approve the protected deployment, then compare
the served manifest's publication ID and WaterGeo commit with the recorded known-good
values. Never replace evidence while claiming the prior checksum or publication
identity. This procedure is documented and covered by package identity tests; it cannot
be exercised against a live Pages deployment until the first real candidate exists.

## Product semantics

The banner's publication time comes from `manifest.generated_at`. Publisher
observation/publication time and WaterGeo retrieval time remain separate. Operational
layers are latest accepted publisher snapshots, not live feeds. Static mode offers
bounded filtering and explicitly marks API-only drill-downs. WaterGeo is an independent
open-source project and is not endorsed by Ofwat, the Environment Agency, or a water
company.

No complete real multi-source artifact has been built or published. Local evidence is
available for only part of the portfolio, and the official Ofwat workbook still needs
the documented manual download, dictionary review and preparation step.
