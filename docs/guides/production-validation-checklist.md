# External production and Fabric validation checklist

Nothing in this checklist has been provisioned or executed by the repository. For the
Phase 14 public preview, stop after manually validating each dynamic source; step 9
belongs to Phase 15 and recurring production schedules remain disabled.

## DigitalOcean production rehearsal

1. Choose one region after measuring user latency, publisher egress and data residency;
   keep App Platform, Spaces and PostgreSQL together where private routing permits.
2. Create managed PostgreSQL with PostGIS, trusted sources and backups. Create separate
   migration, ingestion and app roles; require `verify-full` with the provider CA.
3. Create a private encrypted Spaces bucket. Enable and verify object versioning,
   access logs and retention. Give write/read credentials only to ingestion jobs.
4. Run migration `0011` as a one-shot job using the exact API image digest. Verify the
   revision and stop it before API rollout.
5. Deploy the API digest without autodeploy. Configure trusted hosts, read-only database
   credentials, CA mount, freshness thresholds and `/health`/`/ready` probes.
6. Deploy the commit-scoped `web/dist` artifact. Route `/v1`, `/health` and `/ready` to
   the API and `/` to the explorer under one public origin.
7. Run one manual operator-image refresh per accepted source. Verify object versions,
   archive hashes and the database manifest reference before enabling schedules.
8. Bootstrap static sources, then dynamic sources. Never schedule global history or
   observation retrievals.
9. Enable Hydrology hourly, Thames every 15 minutes and Water Quality metadata daily
   only after manual success. Confirm advisory-lock overlap exits safely.
10. Add DNS/TLS after starter-domain smoke tests. Exercise health, readiness, OpenAPI,
    source status, representative data, explorer and failure states.
11. Configure HTTP error/latency, restart, database, migration, refresh, archive,
    freshness and backup alerts with named owners.
12. Restore a backup to an isolated cluster, replay archived evidence, record RPO/RTO,
    and remove only the rehearsal resources.

See DigitalOcean's [App spec](https://docs.digitalocean.com/products/app-platform/reference/app-spec/)
and [scheduled jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/).

## Fabric tenant validation

1. Create or select a capacity-backed workspace and Lakehouse; record the validation
   owner and tenant/workspace/Lakehouse identities.
2. Build a GeoParquet export and run `examples/fabric/validate_bundle.py`.
3. Upload the unchanged directory to `Files/watergeo/<entity>/<snapshot>/`; compare
   OneLake filenames and byte sizes.
4. Attach the Lakehouse to a notebook and run `tenant_validation_notebook.py`. Record
   checksum verification, row count, schema and snapshot/source columns.
5. Confirm the consumer-owned Delta table uses `errorifexists`; rerun and verify it
   refuses overwrite. Query it from the SQL analytics endpoint if enabled.
6. Add water-supply GeoJSON or PMTiles to Fabric Maps. Label PMTiles as a simplified
   derivative. Use Thames point GeoJSON as a snapshot layer, never as a live stream.
7. Test a bounded GeoJSON reference layer plus Delta attributes in Power BI/Azure Maps.
   Keep snapshot, retrieval time, source and attribution visible.
8. Record screenshots, capacity/runtime and preview status. Claim tenant validation only
   after applicable steps pass.

Microsoft documents [OneLake upload and Delta](https://learn.microsoft.com/en-us/fabric/onelake/create-lakehouse-onelake),
[notebook loading](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-notebook-load-data)
and [Lakehouse Map layers](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/map/about-lakehouse-layers).
