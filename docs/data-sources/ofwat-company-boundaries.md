# Source assessment: Ofwat water-company boundaries

Reviewed **17 September 2026**. Assessment scope: public documentation and downloaded
files; no ingestion or new application dependencies. A subsequent
[schema milestone](../adr/0002-water-supply-snapshots.md) adds empty tables and
synthetic geometry tests, without loading these files.

## Recommendation

**Preferred first source; the publisher's OGL declaration is confirmed.** Proceed
with water-supply schema design and geometry tests using synthetic fixtures. Keep
sewerage as a separately identified future dataset. The exact OGL edition remains
unverified: resolve the edition and final attribution before integrating real data,
in accordance with this project's source-acceptance requirements. Publisher contact
is not a prerequisite for the design and synthetic-test work.

The initial product should answer **which published supply areas cover a point in
this dated snapshot**. It must not promise the definitive current supplier for a
property. Model source areas first; company identity needs separate reconciliation.

## 1. Publisher, distribution, and meaning

- **Originator:** Water Services Regulation Authority (Ofwat), with Ordnance Survey
  support in digitisation. Ofwat points users to Parliament for downloads. Its
  [sector overview](https://www.ofwat.gov.uk/regulated-companies/ofwat-industry-overview/)
  was available through indexed official text; direct retrieval returned HTTP 403.
- **Distributor:** House of Commons Library. Its
  [source page](https://commonslibrary.parliament.uk/research-briefings/cbp-10541/)
  links separate water-supply and sewerage ZIPs, describing an April 2024 release.
  Its dashboard uses an older release, so inspect the downloads themselves.
- **Coverage:** England and Wales, including regional areas and inset appointments
  (small areas with separately appointed undertakers, often called NAVs). No claim
  of Scotland/Northern Ireland coverage or current completeness is justified.
- **Meaning:** digitised appointed service areas for analysis, not legal boundary
  records. Source record notices exclude some premises-level exceptions, warn of
  coastline approximation and omitted islands, and identify specific problem areas.

Water supply and sewerage are separate services. Regional coverage, an inset area,
and a company's name are different concepts; do not collapse them into one record.

An alternative checked was the Environment Agency's
[Water Resource Zones](https://environment.data.gov.uk/dataset/72a77500-d465-11e4-a8b3-f0def148f590).
Those are planning/supply resource zones collated from companies, not a substitute
for the appointed service-area meaning required here. It is not assessed further.

## 2. Licence evidence and remaining question

Ofwat's indexed sector overview, the Commons page, and every downloaded record's
`Licence` field explicitly declare the **Open Government Licence (OGL)**. This is
positive licensing evidence, not an inference from public availability. The ZIPs
contain only Shapefile components:
there is no separate licence file, copyright notice, or metadata sidecar. The
accessible dataset material does not identify an OGL edition or prescribe a
dataset-specific attribution statement. The Ofwat page's licence-link target could
not be inspected because direct requests returned 403. Do not infer an edition
from unrelated Ofwat publications or the year of this release.

### Follow-up public research, 17 September 2026

- The National Archives' [guidance for OGL users](https://cdn.nationalarchives.gov.uk/documents/information-management/ogl-user-guidance.pdf)
  explains that an express OGL declaration authorises reuse under its terms without
  registration or an application. If no bespoke attribution is supplied, credit
  the source using the information available and preserve existing rights notices.
  **Missing bespoke attribution alone does not require an email to the publisher.**
- [Data.gov.uk's metadata guidance](https://guidance.data.gov.uk/publish_and_manage_data/harvest_or_add_data/harvest_data/dcat/)
  accepts either a licence URI or the title `Open Government Licence`. An
  unversioned title is therefore recognised catalogue metadata; this does not
  establish which edition applies to this particular archive.
- The National Archives' [OGL overview](https://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/uk-government-licensing-framework/open-government-licence/)
  describes the three editions as substantially similar, while saying providers
  specify the applicable edition. The [provider guidance](https://cdn.nationalarchives.gov.uk/documents/information-management/ogl-information-provider-guidance.pdf)
  includes an unversioned OGL hyperlink example. Neither document proves this
  dataset is specifically OGL v3.0.

**Assessment:** the open-licence grant is established; the edition is an unresolved
metadata/terms detail. The earlier requirement to obtain a bespoke attribution
statement from Ofwat was too strong. Preserve the declared licence as
`Open Government Licence`, with edition recorded as unknown, rather than silently
normalising it to `OGL-UK-3.0`. Under this project's instruction to resolve unclear
terms before integration, keep real-data integration pending while design and
synthetic tests proceed. No enquiry has been sent or is required from the maintainer
to begin that work.

### Comparable public projects

These are primary descriptions of each project's own use, not licence grants to
WaterGeo UK. No implementation code was copied or independently audited.

| Project | Publicly documented use | Useful lesson and limit |
| --- | --- | --- |
| [OpenPostcodes sources](https://openpostcodes.uk/sources) | Its API's water and sewerage fields use Ofwat v1.5, April 2024, via Commons. It labels the data OGL and links to v3.0; code is separately described as MIT. | A close precedent for the intended API and separate code/data licensing. Its v3.0 link is the project's assertion, not confirmation by Ofwat. |
| [MOSL water-switching map](https://mosl.co.uk/market-insight/market-functions/switching-activity/water-switch-rates-by-wholesale-region) | Credits Ofwat v1_4 dated 25 May 2022 and assigns postal sectors using their centre points. | Credit the exact release and explain spatial approximations. Its postal-boundary copyright notices belong to its combined map, not automatically to our Ofwat-only data. |

For WaterGeo UK, retain separate water/sewerage layers, source dates, attribution,
and spatial caveats. These precedents do not justify reporting a single definitive
current property supplier from a dated polygon match.

### Attribution to carry into implementation

[OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
permits copying, adaptation, and commercial/non-commercial redistribution of
covered information, subject to its conditions and exclusions. That supports
local persistence and API reuse **if that edition is confirmed for these files**.
Its default attribution, when no specific statement is supplied, is:

> Contains public sector information licensed under the Open Government Licence v3.0.

This is a conditional attribution candidate, **not a claim that the edition has
been verified**. Separately credit Ofwat as originator, Commons Library as
distributor, and retain the Ordnance Survey digitisation provenance. No separate
OS attribution wording was found in the inspected files; neither invent a licence
number nor assume an unrelated OS licence applies.

The source credit can already identify **Ofwat water-supply boundaries, release
v1_5 (April 2024), distributed by the House of Commons Library; digitised by Ofwat
with Ordnance Survey support**, linking the source page and archive. This is a
proposed project credit, not publisher-prescribed wording, and does not replace any
edition-specific mandatory statement.

**Before real-data integration:** verify a dataset-specific edition reference and
finalise the associated attribution. A publisher licence-link target or public
clarification could supply that evidence; another project's choice cannot. Retain
the original licence/provenance notices and the evidence URLs. Keep the repository's
MIT licence separate from the data licence and never imply publisher endorsement.

## 3. Exact files inspected

Both public HTTPS downloads returned HTTP 200 without authentication. Actual
response sizes differ from the sizes displayed on the landing page.

| Property | Water supply | Sewerage |
| --- | --- | --- |
| Direct archive | [WaterSupplyAreas_incNAVsv1_5.zip](https://data.parliament.uk/resources/constituencystatistics/water/WaterSupplyAreas_incNAVsv1_5.zip) | [SewerageServicesAreas_incNAVsv1_5a.zip](https://data.parliament.uk/resources/constituencystatistics/water/SewerageServicesAreas_incNAVsv1_5a.zip) |
| Bytes received | 15,192,919 | 8,092,181 |
| HTTP Last-Modified (UTC) | 2024-04-18 13:38:40 | 2024-06-10 17:17:43 |
| Feature count | 1,141 | 748 |
| Source `Version`, every row | `1_5` | `1_5` |
| Source `LastUpdate`, every row | 2024-04-25 | 2024-04-25 |
| Source `Created`, every row | 2020-08-04 | 2020-08-04 |
| Distinct `COMPANY` strings | 25 | 21 |
| Distinct `Acronym` strings | 24 | 21 |
| Decoded Polygon / MultiPolygon | 1,086 / 55 | 711 / 37 |
| Invalid / empty geometries | 5 / 0 | 1 / 0 |
| Missing grant dates | 36 | 13 |
| Rows with source warnings | 6 | 4 |

SHA-256 fingerprints of the downloaded ZIP bytes:

```text
water:    5852ec4481af0ab27e43a2d0d142ca0b55b7a4415eedf68ebe2a20a21fe41f78
sewerage: 48129b880cad01729215a9a6db38d0328302df0e7fdb5a2257cc23d75bdfdd74
```

Each archive contains `.shp`, `.shx`, `.dbf`, and `.prj`. Both Shapefile headers use
type 5 (Polygon, including multipart records). The projection WKT identifies
**British National Grid / OSGB36, EPSG:27700**, with coordinates in metres.
These coordinates are not longitude/latitude.

No `.cpg` encoding declaration exists and the DBF language-driver byte is zero.
Strict UTF-8 decoding succeeded for every record, including `Dŵr Cymru`. Record
UTF-8 as an observed property of these fingerprints, not a guaranteed future
contract; do not silently replace undecodable text in later releases.

## 4. Actual schema and identifiers

Both layers contain these 17 fields. `C` means DBF character, `N` numeric, `D` date.
Field order differs between archives; match fields by name.

| Exact source field(s) | DBF type / width | Interpretation and handling |
| --- | --- | --- |
| `ID` | N(10, 0) | Source area identifier, not a company identifier. |
| `AreaServed` | C(80) | Preserve original area label. |
| `COMPANY`, `Acronym` | C(254) each | Publisher labels; do not assume stable legal-entity IDs. |
| `CoType`, `AreaType` | C(254) each | Preserve classification even where inconsistent. |
| `Date Grant` | D(8) | Includes raw `00000000`; decode to null, retain raw provenance. |
| `Created`, `LastUpdate` | D(8) each | Dates, not observation timestamps or ingestion times. |
| `Version`, `Revisions` | C(254) each | Preserve source revision information. |
| `Disclaimer`, `Disclaim2`, `Disclaim3`, `Provenance`, `WARNINGS` | C(254) each | Retain caveats and lineage; warnings are often blank. |
| `Licence` | Water C(250); sewerage C(254) | Preserve the original licence declaration. |

`ID` is unique within each inspected layer: water IDs span 1–1,141 and sewerage
IDs 1–748. **748 IDs occur in both layers.** For example, ID 7 labels Dŵr Cymru in
water and Isles of Scilly in sewerage. A cross-layer join on `ID` is therefore wrong.
No stability guarantee across releases was found.

Proposed source-record identity is `(dataset, snapshot fingerprint, source ID)`.
Keep company identifiers separate; do not turn names or acronyms directly into
canonical company keys. An internal stable area identity across releases should
wait for evidence of identifier continuity.

## 5. Data-quality findings that affect implementation

These are **local measurements of the downloaded files**, not publisher guarantees:

- Water IDs **1, 4, 6, 28, 30** have self-intersections; sewerage ID **11** has
  nested holes under the recorded GEOS version. Do not silently repair or drop
  these areas. Decide and test a geometry-repair policy before publishing coverage.
  Preserve original bytes and record any repair algorithm/version and its effects.
- Water IDs **888 and 1117** are labelled `Whole sewerage services area`.
  Sewerage IDs **6 and 7** are labelled `Part of water supply area`. Derive service
  type from dataset membership; keep and flag the contradictory source label.
- There are **1,104 water** and **735 sewerage** rows labelled `inset`. These are
  not counts of distinct companies. Company labels include historical variants;
  names/acronyms cannot yet provide reliable cross-dataset reconciliation.
- Source warnings identify boundary corrections and an overlapping application.
  Per-feature validity does not establish an overlap-free or complete coverage map.
  Inter-feature overlaps, gaps, and legal accuracy were **not** tested in this review.
- The sewerage archive suffix is `v1_5a` but records say `1_5`. Water's HTTP
  Last-Modified precedes its record-level LastUpdate. Store archive identity,
  HTTP metadata, and source dates separately; none proves current coverage.

## 6. Retrieval and update approach, once the gates are resolved

No API contract, incremental feed, fixed refresh schedule, or rate-limit policy
was identified for these downloads. The Commons page describes updating when
Ofwat provides new data and cautions that inset appointments change regularly.
The linked release is a dated snapshot, not evidence that no newer boundaries exist.

Recommended first implementation:

1. Fetch the approved water-supply URL with bounded timeouts/download sizes and
   controlled redirects. Use conditional HTTP requests when supported; use a
   content hash as the snapshot identity, not just the filename or `Version` field.
2. Keep original ZIP bytes outside Git, alongside retrieval time, URL, safe HTTP
   validators, byte count, checksum, licence evidence, and transformation version.
   Do not retain cookies or authentication headers as provenance.
3. Validate archive members/size, expected schema, decoding, IDs, dates, CRS, and
   geometries before publishing a replacement snapshot. On failure, keep the last
   accepted snapshot available with its date. Never publish an unnoticed partial load.
4. Preserve the source CRS and source fields. A future PostGIS model can store
   validated area geometries as MultiPolygon in EPSG:27700, transforming explicitly
   to EPSG:4326 for longitude/latitude GeoJSON. Specify transformation accuracy and
   required grids before implementation; no transformation was performed here.
5. Replace a dataset snapshot atomically after validation. Repeated ingestion of
   identical bytes should be a no-op. Treat removed IDs as absent from the new
   snapshot, not as instructions to erase history or other service layers.
6. Return dated area matches with source IDs, warnings, and provenance. Establish
   explicit behaviour for overlapping polygons and boundary points; never choose
   the first match and claim it is the definitive property supplier.

This suggests separate dataset/snapshot metadata and source-area records, not a
generic observation table. Detailed tables and endpoints remain for the next design.

## 7. Evidence, limits, and next action

[The accompanying profile](ofwat-company-boundaries-profile.json) records exact
fields, sizes, HTTP validators, bounds, counts, anomaly IDs, and inspection-library
versions. Archives and the inspection environment stayed in temporary storage;
neither data files nor geospatial dependencies were added to the application.

Method: inspect ZIP/DBF/SHP headers; read every record using PyShp 3.1.6 with strict
UTF-8; convert each original shape through its GeoJSON interface to Shapely 2.1.2;
evaluate `is_valid` / `explain_validity` using GEOS 3.13.1; identify the unchanged
projection WKT using PyProj 3.8.0 / PROJ 9.8.1. Counts are for this decode, before
repair or reprojection. The profile is evidence, not an executable ingestion contract.

**Schema milestone completed:** migration `0002` and synthetic PostGIS tests enforce
strict geometry acceptance; see the [decision](../adr/0002-water-supply-snapshots.md).
**Next action:** evaluate repair behaviour on synthetic cases and define the
evidence needed before permitting any repaired geometry. Resolve the exact OGL
edition and final attribution before loading real data; then implement one snapshot
end to end. This assessment does not
authorise inventing missing licence terms, correcting publisher fields without
lineage, or treating these snapshots as current legal supplier records.
