# Phase 5 public HTTP contract audit

Status: reviewed against FastAPI OpenAPI generation on 2026-09-23.

The repository's FastAPI routes and response models are authoritative. WaterGeo
currently exposes 33 read-only `GET` operations. The first-party Python client uses
HTTP only and validates successful responses against those Pydantic contracts.

## Route inventory

| Domain | Routes | Pagination and pinning |
| --- | --- | --- |
| Operations | `/health`, `/ready` | None. Readiness returns its typed body with HTTP 503 when unavailable. |
| Sources | `/v1/sources/status` | None. Ages describe accepted local evidence at `checked_at`. |
| Water supply | dataset, areas, at-point, area detail, area geometry | Area lists use `after_id`; the reviewed release is immutable. Geometry is `application/geo+json`. |
| Hydrology | dataset, stations, nearby stations, station detail | Station lists use `after_id`; normal lists accept `snapshot_id`. Nearby search and detail select the current snapshot. |
| Hydrology history | `/v1/hydrology/history/{retrieval_id}` | The retrieval ID pins evidence; observations use aware timestamp `after`. |
| Catchments | dataset; lists/details for four hierarchy levels; Water Body geometry | Lists use `after_id` and `snapshot_id`. Detail routes select the current reviewed snapshot. Geometry is `application/geo+json`. |
| Water Quality | dataset, sampling-point list/near/detail | Routes accept `snapshot_id`; lists use opaque `after_id`. Sampling-point IDs are opaque and can contain `/`. |
| Water Quality observations | `/v1/water-quality/observations/{retrieval_id}` | The retrieval ID pins evidence; observations use opaque `after_id`. |
| Severn Trent reservoir levels | dataset, reservoir list/near/detail/readings | Routes accept `snapshot_id`; reservoirs use `after_id`, readings use aware timestamp `after`. |

All list page sizes are bounded by the API. Most entity lists allow 100 records.
Hydrology history allows 1,000; Water Quality observations and reservoir readings
allow 100. Nearby searches are bounded and are not multi-page iterators.

## Shared response behavior

- Unknown entities or retrieval IDs return 404 after a dataset is available.
- Invalid paths, query values, unknown query parameters, or naive history cursors
  return 422.
- Missing datasets, database failures, validation failures at the persistence boundary,
  and reviewed geometry contract failures return 503 with a short `detail` body.
- Water-supply and Water Body geometry endpoints use `application/geo+json`; other
  successful routes use `application/json`.
- API datetimes with source timezone semantics are timezone-aware. Water Quality
  `observed_at_text` remains publisher text because its timezone is unspecified.
- Dataset models carry publisher, licence, attribution, content hashes, retrieval
  timestamps, normalization versions, and domain caveats. Geometry and observation
  responses retain their domain-specific provenance.

## SDK decisions

The SDK re-exports the authoritative response models through
`watergeo.client.models` under clear domain names. The API and SDK currently ship in
the same distribution, so a copied schema would create drift without providing a
separate compatibility boundary. Client transport code does not import database or
ingestion operations.

Iterators pin the `snapshot_id` returned by their first page whenever the server
offers snapshot selection. Retrieval-based iterators remain pinned by retrieval ID.
Every iterator rejects repeated cursors and enforces explicit page and record limits.

## OpenAPI decision

No generated OpenAPI artifact is committed. The schema is already generated
deterministically from the application and is available from a running local server
at `/openapi.json`. `tests/test_api.py::test_openapi_documents_public_endpoints`
acts as route drift protection. Developers can export it with:

```bash
curl --fail http://127.0.0.1:8000/openapi.json > openapi.json
```

A generated client was rejected for this milestone: the hand-maintained surface is
small, preserves domain names, and has dedicated pagination and error behavior that
would otherwise need a wrapper.
