"""Tests for strict Ofwat boundary source validation."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import shapefile
from pyproj import CRS

from watergeo.ingestion.ofwat_boundary_validation import (
    BoundaryValidationContract,
    BoundaryValidationError,
    validate_boundary_archive,
    write_validation_report,
)

FIELDS = (
    ("ID", "N", 10, 0),
    ("Version", "C", 10, 0),
)


def _fixture_archive(
    tmp_path: Path,
    *,
    epsg: int = 27700,
    include_invalid: bool = True,
) -> tuple[Path, BoundaryValidationContract]:
    shp = io.BytesIO()
    shx = io.BytesIO()
    dbf = io.BytesIO()

    writer = shapefile.Writer(
        shp=shp,
        shx=shx,
        dbf=dbf,
        shapeType=shapefile.POLYGON,
        encoding="utf-8",
    )

    writer.field(
        "ID",
        "N",
        size=10,
        decimal=0,
    )
    writer.field(
        "Version",
        "C",
        size=10,
    )

    writer.poly(
        [
            [
                (0, 0),
                (0, 10),
                (10, 10),
                (10, 0),
                (0, 0),
            ]
        ]
    )
    writer.record(
        1,
        "test",
    )

    if include_invalid:
        writer.poly(
            [
                [
                    (20, 0),
                    (22, 2),
                    (20, 2),
                    (22, 0),
                    (20, 0),
                ]
            ]
        )
        writer.record(
            2,
            "test",
        )

    writer.close()

    basename = "fixture"
    archive_path = tmp_path / "fixture.zip"

    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        archive.writestr(
            f"{basename}.shp",
            shp.getvalue(),
        )
        archive.writestr(
            f"{basename}.shx",
            shx.getvalue(),
        )
        archive.writestr(
            f"{basename}.dbf",
            dbf.getvalue(),
        )
        archive.writestr(
            f"{basename}.prj",
            CRS.from_epsg(epsg).to_wkt().encode("utf-8"),
        )

    payload = archive_path.read_bytes()

    record_count = 2 if include_invalid else 1

    invalid_ids = frozenset({2}) if include_invalid else frozenset()

    contract = BoundaryValidationContract(
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_basename=basename,
        expected_fields=FIELDS,
        expected_epsg=27700,
        expected_record_count=record_count,
        expected_shape_type=shapefile.POLYGON,
        expected_ids=frozenset(
            range(
                1,
                record_count + 1,
            )
        ),
        expected_geometry_types={
            "Polygon": record_count,
        },
        expected_invalid_ids=invalid_ids,
        expected_version="test",
    )

    return archive_path, contract


def test_validates_contract_and_reports_invalid_geometry(
    tmp_path: Path,
) -> None:
    archive_path, contract = _fixture_archive(tmp_path)

    report = validate_boundary_archive(
        archive_path,
        contract=contract,
    )

    assert report.record_count == 2
    assert report.epsg == 27700
    assert report.geometry_types == {
        "Polygon": 2,
    }
    assert [item.source_id for item in report.invalid_geometries] == [2]
    assert report.canonical_load_eligible is False


def test_validation_report_is_deterministic(
    tmp_path: Path,
) -> None:
    archive_path, contract = _fixture_archive(tmp_path)

    report = validate_boundary_archive(
        archive_path,
        contract=contract,
    )

    output_root = tmp_path / "reports"

    first_path = write_validation_report(
        report,
        output_root=output_root,
    )

    first = first_path.read_bytes()

    second_path = write_validation_report(
        report,
        output_root=output_root,
    )

    assert second_path == first_path
    assert second_path.read_bytes() == first

    decoded = json.loads(first)

    assert decoded["source_sha256"] == contract.expected_sha256
    assert "retrieved_at" not in decoded


def test_wrong_crs_is_rejected(
    tmp_path: Path,
) -> None:
    archive_path, contract = _fixture_archive(
        tmp_path,
        epsg=4326,
    )

    with pytest.raises(
        BoundaryValidationError,
        match="CRS",
    ):
        validate_boundary_archive(
            archive_path,
            contract=contract,
        )


def test_unexpected_invalid_geometry_set_is_rejected(
    tmp_path: Path,
) -> None:
    archive_path, contract = _fixture_archive(tmp_path)

    strict_contract = BoundaryValidationContract(
        expected_sha256=contract.expected_sha256,
        expected_basename=contract.expected_basename,
        expected_fields=contract.expected_fields,
        expected_epsg=contract.expected_epsg,
        expected_record_count=(contract.expected_record_count),
        expected_shape_type=contract.expected_shape_type,
        expected_ids=contract.expected_ids,
        expected_geometry_types=(contract.expected_geometry_types),
        expected_invalid_ids=frozenset(),
        expected_version=contract.expected_version,
    )

    with pytest.raises(
        BoundaryValidationError,
        match="Invalid geometry IDs",
    ):
        validate_boundary_archive(
            archive_path,
            contract=strict_contract,
        )


def test_tampered_archive_is_rejected_before_decode(
    tmp_path: Path,
) -> None:
    archive_path, contract = _fixture_archive(tmp_path)

    archive_path.write_bytes(archive_path.read_bytes() + b"tamper")

    with pytest.raises(
        BoundaryValidationError,
        match="SHA-256",
    ):
        validate_boundary_archive(
            archive_path,
            contract=contract,
        )
