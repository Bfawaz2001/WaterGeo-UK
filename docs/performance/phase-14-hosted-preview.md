# Phase 14 hosted-preview evidence

**Status: pending external provisioning.**

Provider contracts and list pricing were reviewed against official DigitalOcean
documentation on 28 September 2026. The repository now contains a maintenance-gated
App Platform spec, immutable three-image publication contract, verified-TLS CA wrapper,
managed database role tooling, private/versioned evidence checks and a non-mutating
preflight. No provider resources, public URL, deployment timings, resource IDs or live
smoke results exist yet.

The reviewed baseline estimate is US$30.15/month before tax, transfer/storage overages
and job runtime: US$10 for two 512 MiB App Platform services, US$15.15 for the smallest
1 GiB Managed PostgreSQL plan, and US$5 for Spaces Standard. Migration and temporary
bootstrap jobs are runtime-billed and are expected to add cents, subject to actual
duration. This estimate must be reconfirmed immediately before provisioning.

After approved deployment, append only non-secret facts: reviewed `main` commit, image
digests, region, migration revision, deployment/bootstrap timings, six-source status,
external smoke outcome, generated preview URL, TLS/trusted-source/versioning proof and
the revised monthly estimate. Never record credentials or connection strings.
