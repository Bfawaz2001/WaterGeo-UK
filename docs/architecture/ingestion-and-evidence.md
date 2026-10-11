# Ingestion and evidence

Evidence is the reproducibility boundary. A normalized row alone cannot establish
what the publisher returned. Retain the source bytes, retrieval scope, selected
response metadata and SHA-256 before allowing a database publication. Licensing
must be assessed per source before distribution; retained evidence is not
implicitly public just because the original endpoint was public.

## Source-specific contracts

- Ofwat water supply retains the exact reviewed ZIP and manifest. Raw geometry
  validation and approved canonical transformations are distinct decisions.
- EA paginated families retain bounded response bundles with request/page metadata,
  content hashes and completeness checks. History and observations have explicit
  request scopes; neither is an unbounded national archive.
- Thames retains bounded exact `response.json` bytes and retrieval metadata before
  normalization. Only a completed validated manifest is loadable. Malformed or
  schema-changed evidence remains inspectable without being mistaken for acceptance.
- National products retain the raw source bundle and require matching normalized
  product SHA/version on replay. Flood canonical ordering and company workbook/
  dictionary review are source-specific, not generic repair or automatic mapping.

Readers reject incomplete/altered bundles and unsafe file/path inputs under their
own contracts. These files are ignored by Git. Exact response-byte hashes, normalized
product hashes and geometry hashes represent different stages and are not interchangeable.
See the [portfolio](../data-sources/source-portfolio.md) for each concrete reader and
source assessment; there is no single assumed manifest shape across all families.

## Atomic acceptance and recovery

`operations/refresh.py` supervises fetch → validate → load while holding a source
advisory lock. Publication checks lock ownership; normal cleanup explicitly unlocks
and invalidates the connection so a locked session cannot return to the pool.
The loader's transaction inserts the accepted snapshot and entities together.
Validation/load failure leaves the previous accepted snapshot available. A process
interrupted near commit can have an uncertain outcome: retry the retained bundle
and verify the existing content rather than deleting/replacing rows.

A source lock is cooperative concurrency control, not distributed fencing through
arbitrary database partitions. Deadlines and source-specific retry/pacing limits
remain necessary. See [source operations](../guides/source-operations.md).

## Durable evidence and publication packages

Local ignored directories are suitable for development, not a durable backup promise.
Scheduled production refresh uses private versioned S3-compatible evidence storage;
see [evidence storage](../guides/evidence-storage.md) and
[retention strategy](data-retention-strategy.md).

The static handoff packages ten already accepted source inputs with evidence/replay
manifests, hashes, bounded safe members and the reviewed WaterGeo commit. A private
draft release carries exactly the governed archive; repository release/checksum pins
select it. Independent validation and replay are required before public assets are
built. The package is not a public dataset download and must not leak into the site.

Draft-release asset access required a single-repository fine-grained token with
Contents read/write (push-level permission). Do not generalize that requirement into
organization-wide access; keep it in the protected build environment. See the
[static publication contract](../deployment/zero-cost-static-preview.md).
