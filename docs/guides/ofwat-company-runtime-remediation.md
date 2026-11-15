# Remaining company-view runtime remediation

This is a separate operational follow-up. The service-boundary export PR neither
changes the live database/runtime nor broadens a geometry acceptance contract.

## Recorded failure

The [read-only baseline diagnosis](../data-sources/ofwat-company-runtime-diagnosis.json)
scanned 24 company geometry endpoints: 20 returned HTTP 200; AFW, ANH, SBB and SEW
returned HTTP 503. Their inventories were present. Source feature IDs 3, 4, 16 and
21 matched the reviewed canonical WKB hashes, but the projected output hashes
matched none of the approved ADR 0006 variants. These four outputs were below the
8 MiB feature limit: their errors were not size failures.

The local runtime reported PostGIS 3.7.0, GEOS 3.15.0 and PROJ 9.9.0, with core
procedures at 3.6.4 and an upgrade warning. Runtime drift explains why a previously
accepted canonical snapshot can fail the separate presentation guard. The newly
verified source-preserving analytical bundle does not approve those new outputs.

## Remediation options requiring a separate reviewed change

1. Restore a coherent runtime matching a previously reviewed presentation
   environment, using pinned container/dependency/grid artifacts. Rehearse against
   a disposable database before changing any operational environment. Do not alter
   canonical rows or re-ingest merely to suppress a presentation failure.
2. Alternatively, assess the changed runtime under the existing presentation
   assessment process. Record exact library/container/grid versions, all feature
   validity results, input and output fingerprints, component/hole counts, geometry
   effects and source-data invariance. Review any new output contract under a new
   presentation version; an observed valid output is not automatically approved.

Both paths require a full 1,141-feature scan, all 24 company inventory checks,
canonical/source-field digest invariance, synthetic fail-closed tests, native
runtime evidence and normal request-timeout/response-size checks. A failed hash
must remain HTTP 503. Do not add the newly observed hashes to an allow-list just
to make requests pass. Do not substitute simplified overview geometry for an
exact company boundary.

## Reproduce the read-only endpoint scan

```sh
uv run --locked python scripts/diagnose_ofwat_companies.py \
  --base-url http://127.0.0.1:8000 --output /tmp/ofwat-company-responses.json
```

The canonical/presentation policy is defined in ADRs
[0004](../adr/0004-ofwat-v1_5-canonical-transformation.md) and
[0006](../adr/0006-water-supply-wgs84-presentation.md). The existing
`scripts/assess_water_supply_presentation.py` can generate diagnostic evidence
from a loaded reviewed database; diagnosis never authorises a repair or whitelist
change. No deployment, database upgrade or operational write is part of this PR.
