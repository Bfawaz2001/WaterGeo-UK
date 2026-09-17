"""Strict validation for the reviewed Ofwat water-supply boundary snapshot."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import shapefile
from pyproj import CRS
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity

from watergeo.ingestion.ofwat_boundaries import OFWAT_WATER_SUPPLY_V1_5

VALIDATION_VERSION = 1
EXPECTED_EPSG = 27700
EXPECTED_RECORD_COUNT = 1_141
EXPECTED_SHAPE_TYPE = 5
EXPECTED_INVALID_IDS = frozenset({1, 4, 6, 28, 30})
EXPECTED_GEOMETRY_TYPES = {
    "Polygon": 1_086,
    "MultiPolygon": 55,
}

EXPECTED_FIELDS = (
    ("AreaServed", "C", 80, 0),
    ("ID", "N", 10, 0),
    ("COMPANY", "C", 254, 0),
    ("Acronym", "C", 254, 0),
    ("CoType", "C", 254, 0),
    ("AreaType", "C", 254, 0),
    ("Date Grant", "D", 8, 0),
    ("Disclaimer", "C", 254, 0),
    ("Disclaim2", "C", 254, 0),
    ("Disclaim3", "C", 254, 0),
    ("Provenance", "C", 254, 0),
    ("WARNINGS", "C", 254, 0),
    ("Created", "D", 8, 0),
    ("LastUpdate", "D", 8, 0),
    ("Version", "C", 254, 0),
    ("Revisions", "C", 254, 0),
    ("Licence", "C", 250, 0),
)


class BoundaryValidationError(RuntimeError):
    """Raised when a reviewed boundary snapshot violates its source contract."""


@dataclass(frozen=True, slots=True)
class BoundaryValidationContract:
    expected_sha256: str
    expected_basename: str
    expected_fields: tuple[tuple[str, str, int, int], ...]
    expected_epsg: int
    expected_record_count: int
    expected_shape_type: int
    expected_ids: frozenset[int]
    expected_geometry_types: dict[str, int]
    expected_invalid_ids: frozenset[int]
    expected_version: str


OFWAT_WATER_SUPPLY_V1_5_CONTRACT = BoundaryValidationContract(
    expected_sha256=OFWAT_WATER_SUPPLY_V1_5.expected_sha256,
    expected_basename=OFWAT_WATER_SUPPLY_V1_5.expected_basename,
    expected_fields=EXPECTED_FIELDS,
    expected_epsg=EXPECTED_EPSG,
    expected_record_count=EXPECTED_RECORD_COUNT,
    expected_shape_type=EXPECTED_SHAPE_TYPE,
    expected_ids=frozenset(range(1, EXPECTED_RECORD_COUNT + 1)),
    expected_geometry_types=EXPECTED_GEOMETRY_TYPES,
    expected_invalid_ids=EXPECTED_INVALID_IDS,
    expected_version="1_5",
)


@dataclass(frozen=True, slots=True)
class InvalidGeometry:
    source_id: int
    reason: str


@dataclass(frozen=True, slots=True)
class BoundaryValidationReport:
    validation_version: int
    dataset: str
    release: str
    source_sha256: str
    record_count: int
    epsg: int
    shape_type: int
    fields: tuple[tuple[str, str, int, int], ...]
    geometry_types: dict[str, int]
    empty_geometry_ids: tuple[int, ...]
    invalid_geometries: tuple[InvalidGeometry, ...]
    canonical_load_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def _normalise_fields(reader: Any) -> tuple[tuple[str, str, int, int], ...]:
    fields: list[tuple[str, str, int, int]] = []

    for field in reader.fields[1:]:
        fields.append(
            (
                str(field[0]),
                str(field[1]),
                int(field[2]),
                int(field[3]),
            )
        )

    return tuple(fields)


def _expected_members(
    contract: BoundaryValidationContract,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{contract.expected_basename}{extension}"
            for extension in (".shp", ".shx", ".dbf", ".prj")
        )
    )


def validate_boundary_archive(
    archive_path: Path,
    *,
    contract: BoundaryValidationContract = OFWAT_WATER_SUPPLY_V1_5_CONTRACT,
) -> BoundaryValidationReport:
    """Validate a verified source archive without mutating its data."""

    if not archive_path.is_file() or archive_path.is_symlink():
        raise BoundaryValidationError(
            "Reviewed source archive is missing or is not a regular file."
        )

    digest = _sha256_file(archive_path)

    if digest != contract.expected_sha256:
        raise BoundaryValidationError("Source archive SHA-256 does not match the reviewed release.")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = tuple(sorted(archive.namelist()))

            if members != _expected_members(contract):
                raise BoundaryValidationError(
                    "Source archive members do not match the reviewed Shapefile contract."
                )

            bad_member = archive.testzip()

            if bad_member is not None:
                raise BoundaryValidationError("Source archive failed CRC validation.")

            basename = contract.expected_basename

            shp_bytes = archive.read(f"{basename}.shp")
            shx_bytes = archive.read(f"{basename}.shx")
            dbf_bytes = archive.read(f"{basename}.dbf")
            prj_bytes = archive.read(f"{basename}.prj")

    except zipfile.BadZipFile as error:
        raise BoundaryValidationError("Reviewed source archive is not a valid ZIP file.") from error

    try:
        prj_text = prj_bytes.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as error:
        raise BoundaryValidationError("Projection file is not strict UTF-8.") from error

    try:
        source_crs = CRS.from_wkt(prj_text)
    except Exception as error:
        raise BoundaryValidationError("Projection file does not contain valid CRS WKT.") from error

    source_epsg = source_crs.to_epsg()

    if source_epsg != contract.expected_epsg:
        raise BoundaryValidationError(f"Source CRS does not match EPSG:{contract.expected_epsg}.")

    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(shp_bytes),
            shx=io.BytesIO(shx_bytes),
            dbf=io.BytesIO(dbf_bytes),
            encoding="utf-8",
            encodingErrors="strict",
        )
    except (UnicodeDecodeError, shapefile.ShapefileException) as error:
        raise BoundaryValidationError("Shapefile could not be decoded strictly.") from error

    with reader:
        fields = _normalise_fields(reader)

        if fields != contract.expected_fields:
            raise BoundaryValidationError("DBF field schema does not match the reviewed contract.")

        if int(reader.shapeType) != contract.expected_shape_type:
            raise BoundaryValidationError(
                "Shapefile geometry type does not match the reviewed contract."
            )

        if int(reader.numRecords) != contract.expected_record_count:
            raise BoundaryValidationError("Record count does not match the reviewed contract.")

        ids: list[int] = []
        geometry_types: Counter[str] = Counter()
        empty_geometry_ids: list[int] = []
        invalid_geometries: list[InvalidGeometry] = []

        try:
            for shape_record in reader.iterShapeRecords():
                record = shape_record.record

                source_id_raw = record["ID"]

                if not isinstance(source_id_raw, int):
                    raise BoundaryValidationError("Source ID is not an integer.")

                source_id = source_id_raw
                ids.append(source_id)

                version = record["Version"]

                if version != contract.expected_version:
                    raise BoundaryValidationError(
                        f"Source record {source_id} has an unexpected Version value."
                    )

                geometry = shapely_shape(shape_record.shape.__geo_interface__)

                geometry_types[geometry.geom_type] += 1

                if geometry.is_empty:
                    empty_geometry_ids.append(source_id)
                    continue

                if not geometry.is_valid:
                    invalid_geometries.append(
                        InvalidGeometry(
                            source_id=source_id,
                            reason=explain_validity(geometry),
                        )
                    )

        except UnicodeDecodeError as error:
            raise BoundaryValidationError("DBF content is not strict UTF-8.") from error

    id_set = frozenset(ids)

    if len(ids) != len(id_set):
        raise BoundaryValidationError("Source IDs are not unique.")

    if id_set != contract.expected_ids:
        raise BoundaryValidationError("Source ID set does not match the reviewed contract.")

    geometry_type_counts = dict(sorted(geometry_types.items()))

    if geometry_type_counts != contract.expected_geometry_types:
        raise BoundaryValidationError(
            "Decoded geometry type counts do not match the reviewed contract."
        )

    empty_ids = tuple(sorted(empty_geometry_ids))

    if empty_ids:
        raise BoundaryValidationError("Reviewed source unexpectedly contains empty geometries.")

    invalid_geometries.sort(key=lambda item: item.source_id)

    invalid_ids = frozenset(item.source_id for item in invalid_geometries)

    if invalid_ids != contract.expected_invalid_ids:
        raise BoundaryValidationError(
            "Invalid geometry IDs do not match the reviewed source assessment."
        )

    return BoundaryValidationReport(
        validation_version=VALIDATION_VERSION,
        dataset=OFWAT_WATER_SUPPLY_V1_5.dataset,
        release=OFWAT_WATER_SUPPLY_V1_5.release,
        source_sha256=digest,
        record_count=len(ids),
        epsg=contract.expected_epsg,
        shape_type=contract.expected_shape_type,
        fields=fields,
        geometry_types=geometry_type_counts,
        empty_geometry_ids=empty_ids,
        invalid_geometries=tuple(invalid_geometries),
        canonical_load_eligible=not invalid_geometries,
    )


def write_validation_report(
    report: BoundaryValidationReport,
    *,
    output_root: Path = Path("data/validation/ofwat/water-supply"),
) -> Path:
    """Write a deterministic content-derived validation report atomically."""

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = output_root / f"{report.source_sha256}.validation.json"

    payload = (
        json.dumps(
            report.to_dict(),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )

    fd, temporary_name = tempfile.mkstemp(
        dir=output_root,
        prefix=".validation-",
        suffix=".part",
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(payload)

        os.replace(
            temporary,
            destination,
        )

    except Exception:
        temporary.unlink(
            missing_ok=True,
        )
        raise

    return destination


def validate_reviewed_water_supply(
    *,
    raw_root: Path = Path("data/raw/ofwat/water-supply"),
    output_root: Path = Path("data/validation/ofwat/water-supply"),
) -> tuple[BoundaryValidationReport, Path]:
    """Validate the locally retrieved reviewed water-supply snapshot."""

    archive_path = raw_root / f"{OFWAT_WATER_SUPPLY_V1_5.expected_sha256}.zip"

    report = validate_boundary_archive(archive_path)

    report_path = write_validation_report(
        report,
        output_root=output_root,
    )

    return report, report_path
