# Hosting assessment — 2026-09-24

## Requirements and method

This assessment uses current provider documentation available on 24 September
2026. WaterGeo needs a containerized API, managed PostgreSQL 17 with PostGIS,
private networking, hostname-verified database TLS, secrets, one-shot jobs,
health checks, backups, logs, outbound HTTPS for reviewed publishers, and a later
custom HTTPS domain. Prices are estimates before tax, storage, transfer, job
runtime, or optional services and must be checked before provisioning.

## Options

| Option | Fit and current public pricing | Material limitations |
| --- | --- | --- |
| DigitalOcean App Platform + Managed PostgreSQL | App Platform supports services, deploy-time and scheduled jobs, health checks, encrypted variables and custom domains. A 512 MiB shared service is listed at US$5/month; managed PostgreSQL starts at US$15.15/month, giving a nominal US$20.15/month baseline. Jobs are billed only while running. Managed PostgreSQL documents PostGIS, VPC networking, TLS certificates, trusted sources, daily backups and point-in-time recovery. | App Platform is AMD64 only. Images from GHCR do not automatically redeploy, so release promotion must be deliberate. The managed database's seven-day backup window does not replace independent evidence retention. |
| Google Cloud Run + Cloud SQL for PostgreSQL | Cloud Run provides services and jobs, Secret Manager integration and managed HTTPS. Cloud SQL documents PostGIS and private connectivity from Cloud Run. Scale-to-zero can reduce API compute cost at low traffic. | Pricing is usage-based across Cloud Run, Cloud SQL, networking and logging, so a reliable baseline requires a configured calculator and budget alerts. IAM, VPC access and Cloud SQL connectivity add more operational surface for this project. |
| Render web service + managed PostgreSQL | Render provides private networking, pre-deploy commands, cron jobs, managed TLS and paid PostgreSQL backups/PITR. Managed PostgreSQL supports PostGIS. | Render documents that internal database connections use a self-signed certificate and do not support `verify-ca` or `verify-full`; it recommends `sslmode=require`. That conflicts with WaterGeo's hostname-verification requirement. Free PostgreSQL expires after 30 days and is unsuitable for production. |
| Small DigitalOcean Droplet running containers and PostgreSQL | Droplets start at US$4/month and provide full control. | The operator owns OS patching, firewalling, PostgreSQL/PostGIS upgrades, HA, TLS, monitoring and restore reliability. Droplet backups add 20% for weekly or 30% for daily service. This burden is disproportionate to the current project. |

## Recommendation

Use **DigitalOcean App Platform plus DigitalOcean Managed PostgreSQL** as the
first production target, subject to a final region, budget and connectivity
check. It has the clearest match for PostGIS, private networking, explicit CA
verification, isolated jobs and predictable entry cost. Deploy the API by an
immutable GHCR digest. Run migrations as a deploy-time job with separate
credentials. Keep ingestion outside the API component and do not enable it until
raw evidence has durable encrypted storage.

The repository remains platform-aware rather than platform-locked: its container,
settings, migrations and smoke checks also work on another platform satisfying
the same contracts. No account or resource was created by this assessment.

## Official sources

- DigitalOcean: [App Platform jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/), [pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/), [health checks](https://docs.digitalocean.com/products/app-platform/how-to/manage-health-checks/), [environment variables](https://docs.digitalocean.com/products/app-platform/how-to/use-environment-variables/), and [limits](https://docs.digitalocean.com/products/app-platform/details/limits/).
- DigitalOcean: [managed databases](https://docs.digitalocean.com/products/databases/), [PostgreSQL extensions](https://docs.digitalocean.com/products/databases/postgresql/details/supported-extensions/), [connections and CA](https://docs.digitalocean.com/products/databases/postgresql/how-to/connect/), [trusted sources](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/), [restore behavior](https://docs.digitalocean.com/products/databases/postgresql/how-to/restore-from-backups/), and [managed database pricing](https://www.digitalocean.com/pricing/managed-databases).
- Google Cloud: [Cloud Run overview](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run), [jobs](https://docs.cloud.google.com/run/docs/create-jobs), [job secrets](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets), [Cloud SQL PostGIS](https://docs.cloud.google.com/sql/docs/postgres/extensions), and [Cloud Run connectivity](https://docs.cloud.google.com/sql/docs/postgres/connect-run).
- Render: [private networking](https://render.com/docs/private-network), [PostgreSQL](https://render.com/docs/postgresql), [database connections](https://render.com/docs/postgresql-creating-connecting), [pre-deploy commands](https://render.com/docs/deploys), [cron jobs](https://render.com/docs/cronjobs), and [pricing](https://render.com/pricing).
- DigitalOcean: [Droplet pricing and backup percentages](https://www.digitalocean.com/pricing).
