# Phase 10 production contract

WaterGeo remains provider-neutral and does not require Microsoft Fabric. Production
uses separately operated components:

```text
browser -> HTTPS ingress -> /v1,/health,/ready -> API image -> read-only DB role
                        `-> /                  -> static explorer artifact

migration job -> migration DB role -> managed PostgreSQL/PostGIS
refresh job   -> ingestion DB role + private versioned object storage
```

The API image has no publisher clients, object-store credentials or migration startup
hook. The operator image has publisher retrieval code, the ingestion identity and
object-store credentials, but is not routable. A one-shot migration must finish before
API rollout. Deploy an immutable commit image digest; repository changes never deploy
production automatically.

The ingress owns public TLS and routes same-origin paths. The API continues to reject
untrusted hosts and require `verify-full` database TLS. Browser code uses relative API
URLs, so no CORS exception is required. The separately retained `web/dist` artifact is
the static deployment unit.

Dynamic refresh publication follows: retrieve locally, validate, archive immutably,
read back and verify every object, confirm the source advisory lock, then transact the
database publication. Production configuration accepts only versioned S3-compatible
storage. Hydrology, Water Quality metadata and Thames snapshot manifests record the
durable evidence identity.

This is a repository contract, not evidence that hosting exists. Region, hostnames,
capacity, retention, recovery targets, alert destinations and edge limits remain
operator decisions.
