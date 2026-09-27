# Durable evidence storage

`watergeo.evidence` provides content-addressed local and S3-compatible stores. It
inventories only regular files, rejects symlinks and unsafe paths, hashes every byte,
and writes `evidence-index.json` last. The bundle identity covers source, accepted or
rejected disposition, paths, sizes and SHA-256 values.

Local storage defaults to `data/evidence/` and supports development or a durable
operator-mounted filesystem. S3 storage uses conditional `If-None-Match: *` writes,
requires bucket versioning, records object version IDs, reads every object back and
verifies its size and SHA-256. A retry reuses the same content-addressed identity only
after complete verification; it never overwrites an existing key.

Production ingestion requires:

```text
WATERGEO_SERVICE_ENVIRONMENT=production
WATERGEO_EVIDENCE_BACKEND=s3
WATERGEO_EVIDENCE_S3_ENDPOINT=https://REGION.example-object-storage.invalid
WATERGEO_EVIDENCE_S3_REGION=REGION
WATERGEO_EVIDENCE_S3_BUCKET=PRIVATE_VERSIONED_BUCKET
WATERGEO_EVIDENCE_S3_PREFIX=watergeo/evidence
WATERGEO_EVIDENCE_S3_ACCESS_KEY_ID=...
WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY=...
```

Install the operator-only dependency with `uv sync --locked --extra evidence-s3`.
Credentials belong only to refresh jobs. The API and explorer must not receive them.
Require private bucket access, encryption, versioning, access logs, retention and a
separate deletion role. DigitalOcean Spaces documents its S3-compatible versioning at
<https://docs.digitalocean.com/products/spaces/how-to/enable-versioning/>.

Validated bundles use the `accepted` prefix. If retrieval or validation leaves raw
files, refresh attempts archive them under `rejected` before failing. Rejected evidence
is never passed to a loader. Archive or read-back failure also stops publication. Logs
expose only the phase/outcome, never credentials, raw bodies or paths.
