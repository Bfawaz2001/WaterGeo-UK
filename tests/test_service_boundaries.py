"""Synthetic source archives only; no PCD or downloaded publisher features."""

import hashlib
import io
import json
import math
import zipfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import shapefile
from pyproj import CRS
from shapely.geometry import shape

from watergeo import service_boundaries as product
from watergeo.ingestion.ofwat_boundary_validation import (
    EXPECTED_FIELDS,
    BoundaryValidationError,
)
from watergeo.ingestion.ofwat_canonical import (
    SOURCE_DISCLAIM2,
    SOURCE_DISCLAIM3,
    SOURCE_DISCLAIMER,
    SOURCE_LICENCE_STATEMENT,
    SOURCE_PROVENANCE_STATEMENT,
)

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


@pytest.fixture
def source_pair(tmp_path, monkeypatch, request):
    raw = tmp_path / "raw"
    services, mappings = {}, []
    for service, (source, contract) in product.SERVICES.items():
        buffers = {ext: io.BytesIO() for ext in ("shp", "shx", "dbf")}
        writer = shapefile.Writer(**buffers, shapeType=5, encoding="utf-8", strict=True)
        for name, kind, width, decimal in EXPECTED_FIELDS:
            writer.field(name, kind, size=width, decimal=decimal)
        fields = {
            "AreaServed": "Synthetic inset",
            "COMPANY": "Fixture Water",
            "Acronym": "FIX",
            "CoType": "synthetic NAV",
            "AreaType": "inset",
            "Date Grant": None,
            "Disclaimer": SOURCE_DISCLAIMER,
            "Disclaim2": SOURCE_DISCLAIM2,
            "Disclaim3": SOURCE_DISCLAIM3,
            "Provenance": SOURCE_PROVENANCE_STATEMENT,
            "WARNINGS": "Synthetic fixture",
            "Created": date(2020, 8, 4),
            "LastUpdate": date(2024, 4, 25),
            "Version": "1_5",
            "Revisions": "",
            "Licence": SOURCE_LICENCE_STATEMENT,
        }
        for identifier, coords in [
            (
                1,
                [
                    (400000, 200000),
                    (400000, 200100),
                    (400100, 200100),
                    (400100, 200000),
                    (400000, 200000),
                ],
            ),
            (
                2,
                [
                    (400200, 200000),
                    (400300, 200100),
                    (400200, 200100),
                    (400300, 200000),
                    (400200, 200000),
                ],
            ),
        ]:
            vertices = getattr(request, "param", 0)
            if identifier == 1 and vertices:
                coords = [
                    (
                        400000 + 100 * math.cos(-2 * math.pi * i / vertices),
                        200000 + 100 * math.sin(-2 * math.pi * i / vertices),
                    )
                    for i in range(vertices)
                ]
                coords.append(coords[0])
            writer.poly([coords])
            writer.record(**{**fields, "ID": identifier})
        writer.close()
        root = raw / service
        root.mkdir(parents=True)
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            for ext, data in buffers.items():
                archive.writestr(f"fixture.{ext}", data.getvalue())
            archive.writestr("fixture.prj", CRS.from_epsg(27700).to_wkt())
        data = content.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        source = replace(
            source, expected_sha256=digest, expected_bytes=len(data), expected_basename="fixture"
        )
        contract = replace(
            contract,
            expected_sha256=digest,
            expected_basename="fixture",
            expected_fields=EXPECTED_FIELDS,
            expected_record_count=2,
            expected_ids=frozenset({1, 2}),
            expected_invalid_ids=frozenset({2}),
            expected_geometry_types={"Polygon": 2},
        )
        (root / f"{digest}.zip").write_bytes(data)
        (root / f"{digest}.json").write_bytes(
            product.encode(
                {
                    "dataset": source.dataset,
                    "release": source.release,
                    "source_url": source.source_url,
                    "publisher": source.publisher,
                    "distributor": source.distributor,
                    "licence_name": source.licence_name,
                    "licence_version": None,
                    "sha256": digest,
                    "bytes": len(data),
                }
            )
        )
        services[service] = source, contract
        mappings.append(
            {
                "dataset": source.dataset,
                "COMPANY": "Fixture Water",
                "Acronym": "FIX",
                "company_id": "fixture",
                "company_name": "Fixture Water",
                "review_reference": "synthetic-test-review",
            }
        )
    monkeypatch.setattr(product, "SERVICES", services)
    crosswalk = tmp_path / "crosswalk.json"
    crosswalk.write_bytes(
        product.encode({"review_status": "reviewed_publisher_label_grouping", "mappings": mappings})
    )
    return raw, crosswalk


def build(tmp_path, source_pair):
    raw, crosswalk = source_pair
    output = tmp_path / "bundle"
    manifest = product.build_service_bundle(raw, output, crosswalk)
    return output, manifest


def test_complete_bundle_identity_geometry_and_types(tmp_path, source_pair):
    output, manifest = build(tmp_path, source_pair)
    assert manifest["validation_results"]["feature_count"] == 4
    assert manifest["validation_results"]["source_invalid_count"] == 2
    water = pq.read_table(output / "water-supply.parquet")
    sewer = pq.read_table(output / "sewerage.parquet")
    assert water.schema.field("source_id").type == pa.int64()
    assert water.schema.field("coverage_eligible").type == pa.bool_()
    assert water.schema.field("licence_version").type == pa.string()
    assert water["boundary_id"][0].as_py() != sewer["boundary_id"][0].as_py()
    for service in product.SERVICES:
        rows = pq.read_table(output / f"{service}.parquet").to_pylist()
        assert [r["coverage_eligible"] for r in rows] == [True, False]
        assert all(r["licence_version"] is None for r in rows)
        assert all(json.loads(r["source_fields_json"])["Date Grant"] is None for r in rows)
        assert all(
            hashlib.sha256(r["geometry"]).hexdigest() == r["source_wkb_sha256"] for r in rows
        )
        layer = json.loads((output / f"{service}.geojson").read_bytes())
        assert all(shape(f["geometry"]).geom_type == "Polygon" for f in layer["features"])
    assert product.validate_service_bundle(output) == json.loads(product.encode(manifest))
    with pytest.raises(ValueError, match="destination exists"):
        product.build_service_bundle(source_pair[0], output, source_pair[1])


def test_cross_service_and_snapshot_collisions():
    assert (
        len(
            {
                product.boundary_id(d, s, 7)
                for d in ("water", "sewer")
                for s in ("snapshot-a", "snapshot-b")
            }
        )
        == 4
    )


def test_missing_and_ambiguous_company_mappings(tmp_path, source_pair):
    raw, crosswalk = source_pair
    document = json.loads(crosswalk.read_bytes())
    document["mappings"].pop()
    crosswalk.write_bytes(product.encode(document))
    with pytest.raises(ValueError, match="Missing reviewed company mapping"):
        product.build_service_bundle(raw, tmp_path / "missing", crosswalk)
    document["mappings"] *= 2
    crosswalk.write_bytes(product.encode(document))
    with pytest.raises(ValueError, match="Duplicate"):
        product.read_crosswalk(crosswalk)


@pytest.mark.parametrize("change", ["count", "invalid"])
def test_source_acceptance_is_fail_closed(tmp_path, source_pair, monkeypatch, change):
    source, contract = product.SERVICES["sewerage"]
    altered = replace(
        contract,
        **(
            {"expected_record_count": 3}
            if change == "count"
            else {"expected_invalid_ids": frozenset()}
        ),
    )
    monkeypatch.setitem(product.SERVICES, "sewerage", (source, altered))
    with pytest.raises(BoundaryValidationError):
        product.build_service_bundle(source_pair[0], tmp_path / "bad", source_pair[1])
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("file", ["sewerage.parquet", "areas.parquet", "manifest.json"])
def test_file_and_manifest_checksums(tmp_path, source_pair, file):
    output, _ = build(tmp_path, source_pair)
    with (output / file).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="checksum mismatch"):
        product.validate_service_bundle(output)


def test_licence_metadata_is_not_upgraded(tmp_path, source_pair):
    raw, crosswalk = source_pair
    source = product.SERVICES["sewerage"][0]
    manifest_path = raw / "sewerage" / f"{source.expected_sha256}.json"
    metadata = json.loads(manifest_path.read_bytes())
    metadata["licence_version"] = "3.0"
    manifest_path.write_bytes(product.encode(metadata))
    with pytest.raises(ValueError, match="licence metadata"):
        product.build_service_bundle(raw, tmp_path / "bad", crosswalk)


def test_source_changes_during_export(tmp_path, source_pair, monkeypatch):
    real_digest = product.digest_file
    monkeypatch.setattr(
        product,
        "digest_file",
        lambda path: "0" * 64 if path.suffix == ".zip" else real_digest(path),
    )
    with pytest.raises(ValueError, match="snapshot changed"):
        product.build_service_bundle(source_pair[0], tmp_path / "bad", source_pair[1])


@pytest.mark.parametrize("source_pair", [250_000], indirect=True)
def test_large_company_exports_are_complete_without_collection_size_bypass(tmp_path, source_pair):
    output, manifest = build(tmp_path, source_pair)
    for service in product.SERVICES:
        assert manifest["files"][f"{service}.geojson"]["bytes"] > 8 * 1024 * 1024
        assert pq.read_table(output / f"{service}.parquet").num_rows == 2
    assert pq.read_table(output / "company-area-bridge.parquet").num_rows == 4


def test_fabric_example_preserves_geometry_and_validates_before_reads(
    tmp_path, source_pair, monkeypatch
):
    import runpy
    from types import SimpleNamespace

    output, _ = build(tmp_path, source_pair)
    namespace = runpy.run_path("examples/fabric/ofwat_services_notebook.py")
    read = namespace["read_services"]
    calls = []

    def validate(_mounted, expected):
        calls.append("validated")
        return product.validate_service_bundle(output, expected)

    def parquet(path):
        assert calls and calls[0] == "validated"
        calls.append(path)
        return pq.read_table(output / Path(path).name)

    monkeypatch.setitem(read.__globals__, "validate_service_bundle", validate)
    result = read(
        SimpleNamespace(read=SimpleNamespace(parquet=parquet)),
        "april-2024-v1",
        product.digest_file(output / "manifest.json"),
    )
    assert len(result["frames"]) == 6
    assert result["frames"]["sewerage"].schema.field("geometry").type == pa.binary()
    assert (
        result["frames"]["sewerage"]["source_wkb_sha256"].to_pylist()
        == pq.read_table(output / "sewerage.parquet")["source_wkb_sha256"].to_pylist()
    )
    calls.clear()
    with pytest.raises(ValueError, match="Manifest checksum"):
        read(SimpleNamespace(read=SimpleNamespace(parquet=parquet)), "april-2024-v1", "0" * 64)
    assert calls == ["validated"]


def test_unlisted_bundle_files_are_rejected(tmp_path, source_pair):
    output, _ = build(tmp_path, source_pair)
    (output / "unexpected.txt").write_text("synthetic unlisted content")
    with pytest.raises(ValueError, match="unlisted files"):
        product.validate_service_bundle(output)
