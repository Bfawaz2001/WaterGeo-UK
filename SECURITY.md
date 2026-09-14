# Security

## Reporting

Please do not post credentials, exploit details, or personal data in public issues.
Use GitHub's **Report a vulnerability** option on this repository's Security tab
when private reporting is enabled. If it is unavailable, open an issue requesting
a private reporting channel without including sensitive details. The maintainer
should enable private vulnerability reporting before inviting public use.

Only the current `main` branch is maintained during this pre-release phase.
There is no production deployment or response-time guarantee yet.

## Current controls

- `.env` and local data are ignored by Git; the Docker build context is allowlisted.
- Passwords are required, represented as secret values, and passed to SQLAlchemy
  as structured URL components. Never print settings, raw database errors, or
  connection URLs with password hiding disabled.
- PostgreSQL administrator, migration, and API roles are separate. The API has
  schema usage and table SELECT grants, with no application-table write grants.
- Database connections, pool waits, SQL statements, and locks have timeouts.
- Operational failures expose generic responses and sanitised application logs.
  Application JSON logs use controlled event names. Uvicorn lifecycle/error logs
  retain Uvicorn's format; access logging is disabled in the documented commands.
- The API container is non-root. Compose drops its capabilities, prevents gaining
  privileges, uses a read-only filesystem, and binds ports to loopback.
- CORS is not enabled. Proxy headers are not trusted in local launch commands.
- CI uses read-only tokens except CodeQL's security-result upload permission;
  third-party Actions are pinned to verified commit SHAs. Dependency auditing,
  Dependabot, and CodeQL are configured.

These controls are a development baseline, not a completed public-hosting design.
GitHub secret scanning/push protection, private reporting, and branch protections
are repository settings and must be enabled by the maintainer where available.
Do not enable CodeQL default setup alongside the committed advanced workflow.

## Future integrations and deployment

There is currently no ingestion endpoint or arbitrary outbound URL facility.
Future provider clients must use approved publisher hosts, validate redirects,
bound response sizes and timeouts, and retry only appropriate transient failures.
No internal APIs or credentials may be used.

Before public hosting, review TLS, trusted hosts/proxies, resource and request
limits, rate limiting, database TLS/network access, backup restoration, secret
rotation, and operational monitoring. Local Compose credentials are for local
development; do not reuse them elsewhere.
