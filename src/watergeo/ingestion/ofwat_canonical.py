"""Canonical Ofwat water-supply decoding and atomic PostGIS loading."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import shapefile
import shapely
from shapely import make_valid, to_wkb
from shapely.geometry import MultiPolygon
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity
from sqlalchemy import Connection, Engine, text

from watergeo.core.datasets import OFWAT_WATER_SUPPLY_TRANSFORMATION
from watergeo.ingestion.ofwat_boundaries import (
    OFWAT_WATER_SUPPLY_V1_5,
)
from watergeo.ingestion.ofwat_boundary_validation import (
    EXPECTED_INVALID_IDS,
    EXPECTED_RECORD_COUNT,
    validate_boundary_archive,
)

TRANSFORMATION_VERSION = OFWAT_WATER_SUPPLY_TRANSFORMATION
TRANSFORMATION_METHOD = "structure"
TRANSFORMATION_KEEP_COLLAPSED = False

EXPECTED_SHAPELY_VERSION = "2.1.2"
EXPECTED_GEOS_VERSION = "3.13.1"

ASSESSMENT_VERSION = "ofwat-water-supply-v1_5-repair-assessment-v1"

REVIEW_REFERENCE = "docs/adr/0004-ofwat-v1_5-canonical-transformation.md"

REVIEW_REASON = "Source-specific geometry transformation approved by ADR 0004."

SOURCE_LICENCE_STATEMENT = "This shapefile is published under the Open Government Licence."

SOURCE_PROVENANCE_STATEMENT = (
    "This shapefile has been digitised from the legal "
    "records by the Water Services Regulation Authority "
    "(Ofwat) with support from Ordnance Survey."
)

SOURCE_DISCLAIMER = (
    "This shapefile is designed for geospatial analysis "
    "only. The definitive legal record of areas remains "
    "the maps and other information set out in the "
    "appointments of companies as water and/or sewerage "
    "undertakers and subsequent area variations."
)

SOURCE_DISCLAIM2 = (
    "This shapefile does not include information on any "
    "premises or installations that are located outside "
    "the boundary but included in the area or that are "
    "located inside the boundary but excluded from the area."
)

SOURCE_DISCLAIM3 = (
    "For the purposes of geospatial analysis and visual "
    "display the Mean High Water Line has been used for "
    "any seaward boundary (although the low water mark is "
    "more likely to be the actual boundary) and islands "
    "that are part of the area may have been omitted."
)

LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/"
    "information-management/"
    "re-using-public-sector-information/"
    "uk-government-licensing-framework/"
    "open-government-licence/"
)


class CanonicalIngestionError(RuntimeError):
    """Raised when reviewed canonical-ingestion policy is violated."""


@dataclass(frozen=True, slots=True)
class ReviewedGeometryContract:
    source_wkb_sha256: str
    canonical_wkb_sha256: str
    canonical_type: str
    canonical_parts: int


APPROVED_GEOMETRY_CONTRACTS = {
    1: ReviewedGeometryContract(
        source_wkb_sha256=("084a7f2d30e6e084f0037b2eae63de4a9478d111d30dc9e3494477b530eaa0a3"),
        canonical_wkb_sha256=("8939d2cf392d8b7d9f37b88df7492012cae16f9118db4a152303f459588c2a7f"),
        canonical_type="MultiPolygon",
        canonical_parts=3,
    ),
    4: ReviewedGeometryContract(
        source_wkb_sha256=("0a8de1f1dcc91a2edf60d2238b092681199a1c0b854e44dbb8b59a573bb180aa"),
        canonical_wkb_sha256=("829928770402be6b318f86cf9e9e28212c8d8f6314071db89c3de39e6d01a4a3"),
        canonical_type="MultiPolygon",
        canonical_parts=607,
    ),
    6: ReviewedGeometryContract(
        source_wkb_sha256=("8d12dac0f45ab63fa44c93e7770965e3cdf47d760cd125d80dd6d7301782e8fa"),
        canonical_wkb_sha256=("2a311f09afd4e3aeb3cff8f6b22945514875e680159f524715ba6d183ed06745"),
        canonical_type="MultiPolygon",
        canonical_parts=16,
    ),
    28: ReviewedGeometryContract(
        source_wkb_sha256=("a8d8f564a29d4452afad516c59057253eadf5c888ead89daf17db6a9f0970a7d"),
        canonical_wkb_sha256=("58ed9a8dad021a0d35ff6eeb5fb74310eacc232825ea839187c3d8f1609dd7bc"),
        canonical_type="MultiPolygon",
        canonical_parts=12,
    ),
    30: ReviewedGeometryContract(
        source_wkb_sha256=("4027a26bfb570327bd6866e752a74042c5db673e680366306acc44d2b8ee9364"),
        canonical_wkb_sha256=("d9afd2c91284e189be0f4befdb1049a695f0738c48297990f17308ad3f9db337"),
        canonical_type="MultiPolygon",
        canonical_parts=2,
    ),
}

APPROVED_REPAIR_IDS = frozenset(APPROVED_GEOMETRY_CONTRACTS)


@dataclass(frozen=True, slots=True)
class TransformationProvenance:
    source_id: int
    transformation_id: str
    method: str
    keep_collapsed: bool
    shapely_version: str
    geos_version: str
    invalid_reason: str
    source_decoded_wkb_sha256: str
    canonical_wkb_sha256: str
    review_status: str
    review_reason: str
    review_reference: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CanonicalArea:
    source_id: int
    source_fields: dict[str, Any]
    geometry_wkb: bytes
    transformation: TransformationProvenance | None


@dataclass(frozen=True, slots=True)
class CanonicalSnapshot:
    source_sha256: str
    source_url: str
    source_bytes: int
    retrieved_at: datetime
    publisher: str
    distributor: str
    licence_name: str
    licence_version: str | None
    licence_url: str
    attribution: str
    transformation_version: str
    areas: tuple[CanonicalArea, ...]


@dataclass(frozen=True, slots=True)
class LoadResult:
    snapshot_id: UUID
    status: Literal["inserted", "existing"]
    area_count: int
    transformed_count: int


def _wkb_bytes(geometry: Any) -> bytes:
    raw = to_wkb(
        geometry,
        hex=False,
        byte_order=1,
        include_srid=False,
    )

    if not isinstance(raw, bytes):
        raise CanonicalIngestionError("Shapely did not return binary WKB.")

    return raw


def _wkb_sha256(geometry: Any) -> str:
    return hashlib.sha256(_wkb_bytes(geometry)).hexdigest()


def _part_count(geometry: Any) -> int:
    children = getattr(
        geometry,
        "geoms",
        None,
    )

    if children is None:
        return 1

    return len(children)


def _assert_transformation_runtime() -> None:
    if shapely.__version__ != EXPECTED_SHAPELY_VERSION:
        raise CanonicalIngestionError(
            "Shapely version does not match the reviewed transformation runtime."
        )

    if shapely.geos_version_string != EXPECTED_GEOS_VERSION:
        raise CanonicalIngestionError(
            "GEOS version does not match the reviewed transformation runtime."
        )


def _as_multipolygon(
    geometry: Any,
) -> MultiPolygon:
    if geometry.geom_type == "Polygon":
        result = MultiPolygon([geometry])

    elif geometry.geom_type == "MultiPolygon":
        result = geometry

    else:
        raise CanonicalIngestionError("Canonical geometry is not polygonal.")

    if result.is_empty:
        raise CanonicalIngestionError("Canonical geometry is empty.")

    if result.has_z:
        raise CanonicalIngestionError("Canonical geometry is not two-dimensional.")

    if not result.is_valid:
        raise CanonicalIngestionError("Canonical geometry is invalid.")

    return result


def canonicalise_source_geometry(
    source_id: int,
    geometry: Any,
) -> tuple[
    MultiPolygon,
    TransformationProvenance | None,
]:
    """Apply only the source-specific repair approved by ADR 0004."""

    if geometry.is_empty:
        raise CanonicalIngestionError(f"Source geometry {source_id} is empty.")

    if geometry.geom_type not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise CanonicalIngestionError(f"Source geometry {source_id} is not polygonal.")

    if geometry.has_z:
        raise CanonicalIngestionError(f"Source geometry {source_id} is not two-dimensional.")

    contract = APPROVED_GEOMETRY_CONTRACTS.get(source_id)

    if geometry.is_valid:
        if contract is not None:
            raise CanonicalIngestionError(
                f"Approved repair target {source_id} unexpectedly became valid."
            )

        return (
            _as_multipolygon(geometry),
            None,
        )

    if contract is None:
        raise CanonicalIngestionError(
            f"Invalid source geometry {source_id} has no approved transformation."
        )

    source_hash = _wkb_sha256(geometry)

    if source_hash != contract.source_wkb_sha256:
        raise CanonicalIngestionError(
            f"Source geometry {source_id} does not match its reviewed WKB hash."
        )

    _assert_transformation_runtime()

    invalid_reason = explain_validity(geometry)

    transformed = make_valid(
        geometry,
        method=TRANSFORMATION_METHOD,
        keep_collapsed=(TRANSFORMATION_KEEP_COLLAPSED),
    )

    canonical = _as_multipolygon(transformed)

    canonical_hash = _wkb_sha256(canonical)

    if canonical_hash != contract.canonical_wkb_sha256:
        raise CanonicalIngestionError(
            f"Canonical geometry {source_id} does not match its reviewed WKB hash."
        )

    if canonical.geom_type != contract.canonical_type:
        raise CanonicalIngestionError(
            f"Canonical geometry {source_id} has an unexpected geometry type."
        )

    if _part_count(canonical) != contract.canonical_parts:
        raise CanonicalIngestionError(
            f"Canonical geometry {source_id} has an unexpected part count."
        )

    provenance = TransformationProvenance(
        source_id=source_id,
        transformation_id=(TRANSFORMATION_VERSION),
        method=TRANSFORMATION_METHOD,
        keep_collapsed=(TRANSFORMATION_KEEP_COLLAPSED),
        shapely_version=shapely.__version__,
        geos_version=(shapely.geos_version_string),
        invalid_reason=invalid_reason,
        source_decoded_wkb_sha256=(source_hash),
        canonical_wkb_sha256=(canonical_hash),
        review_status="approved",
        review_reason=REVIEW_REASON,
        review_reference=REVIEW_REFERENCE,
        details={
            "assessment_version": (ASSESSMENT_VERSION),
            "source_geometry_type": (geometry.geom_type),
            "canonical_geometry_type": (canonical.geom_type),
            "canonical_parts": (contract.canonical_parts),
            "hash_encoding": (
                "Little-endian WKB from decoded Shapely geometry, without SRID or normalisation"
            ),
        },
    )

    return canonical, provenance


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    if isinstance(
        value,
        (date, datetime),
    ):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(
        value,
        (list, tuple),
    ):
        return [_json_safe(item) for item in value]

    raise CanonicalIngestionError(f"Unsupported source-field value type: {type(value).__name__}.")


def _validate_publisher_fields(
    source_id: int,
    fields: dict[str, Any],
) -> None:
    expected = {
        "Licence": (SOURCE_LICENCE_STATEMENT),
        "Provenance": (SOURCE_PROVENANCE_STATEMENT),
        "Disclaimer": (SOURCE_DISCLAIMER),
        "Disclaim2": (SOURCE_DISCLAIM2),
        "Disclaim3": (SOURCE_DISCLAIM3),
    }

    for field, expected_value in expected.items():
        if fields.get(field) != expected_value:
            raise CanonicalIngestionError(f"Source record {source_id} has unexpected {field} text.")


def _load_manifest(
    path: Path,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CanonicalIngestionError("Retrieval manifest is missing or is not a regular file.")

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))

    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise CanonicalIngestionError("Retrieval manifest could not be read.") from error

    if not isinstance(
        manifest,
        dict,
    ):
        raise CanonicalIngestionError("Retrieval manifest is not a JSON object.")

    expected: dict[str, Any] = {
        "dataset": (OFWAT_WATER_SUPPLY_V1_5.dataset),
        "release": (OFWAT_WATER_SUPPLY_V1_5.release),
        "source_url": (OFWAT_WATER_SUPPLY_V1_5.source_url),
        "sha256": (OFWAT_WATER_SUPPLY_V1_5.expected_sha256),
        "bytes": (OFWAT_WATER_SUPPLY_V1_5.expected_bytes),
        "publisher": (OFWAT_WATER_SUPPLY_V1_5.publisher),
        "distributor": (OFWAT_WATER_SUPPLY_V1_5.distributor),
        "licence_name": (OFWAT_WATER_SUPPLY_V1_5.licence_name),
        "licence_version": None,
    }

    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise CanonicalIngestionError(
                f"Retrieval manifest does not match reviewed source metadata: {key}."
            )

    return manifest


def _parse_retrieved_at(
    manifest: dict[str, Any],
) -> datetime:
    value = manifest.get("retrieved_at")

    if not isinstance(value, str):
        raise CanonicalIngestionError("Retrieval timestamp is missing.")

    try:
        result = datetime.fromisoformat(value)

    except ValueError as error:
        raise CanonicalIngestionError("Retrieval timestamp is invalid.") from error

    if result.tzinfo is None:
        raise CanonicalIngestionError("Retrieval timestamp is not timezone-aware.")

    return result


def decode_reviewed_water_supply(
    *,
    raw_root: Path = Path("data/raw/ofwat/water-supply"),
) -> CanonicalSnapshot:
    """Decode and canonicalise the exact reviewed Ofwat release."""

    digest = OFWAT_WATER_SUPPLY_V1_5.expected_sha256

    archive_path = raw_root / f"{digest}.zip"

    manifest_path = raw_root / f"{digest}.json"

    validation = validate_boundary_archive(archive_path)

    if validation.source_sha256 != digest:
        raise CanonicalIngestionError(
            "Validated source SHA-256 does not match the reviewed archive."
        )

    if validation.record_count != EXPECTED_RECORD_COUNT:
        raise CanonicalIngestionError(
            "Validated source record count does not match the reviewed contract."
        )

    invalid_ids = frozenset(item.source_id for item in validation.invalid_geometries)

    if invalid_ids != EXPECTED_INVALID_IDS:
        raise CanonicalIngestionError(
            "Validated invalid geometry IDs do not match the source contract."
        )

    if invalid_ids != APPROVED_REPAIR_IDS:
        raise CanonicalIngestionError("Validated invalid geometry IDs do not match ADR 0004.")

    manifest = _load_manifest(manifest_path)

    archive_members = manifest.get("archive_members")

    expected_members = sorted(
        [
            (f"{OFWAT_WATER_SUPPLY_V1_5.expected_basename}{extension}")
            for extension in (
                ".dbf",
                ".prj",
                ".shp",
                ".shx",
            )
        ]
    )

    if archive_members != expected_members:
        raise CanonicalIngestionError(
            "Retrieval manifest archive members do not match the reviewed source."
        )

    basename = OFWAT_WATER_SUPPLY_V1_5.expected_basename

    try:
        with zipfile.ZipFile(archive_path) as archive:
            shp_bytes = archive.read(f"{basename}.shp")
            shx_bytes = archive.read(f"{basename}.shx")
            dbf_bytes = archive.read(f"{basename}.dbf")

    except (
        KeyError,
        zipfile.BadZipFile,
    ) as error:
        raise CanonicalIngestionError(
            "Reviewed source archive could not be opened for canonical decoding."
        ) from error

    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(shp_bytes),
            shx=io.BytesIO(shx_bytes),
            dbf=io.BytesIO(dbf_bytes),
            encoding="utf-8",
            encodingErrors="strict",
        )

    except (
        UnicodeDecodeError,
        shapefile.ShapefileException,
    ) as error:
        raise CanonicalIngestionError(
            "Reviewed Shapefile could not be decoded strictly."
        ) from error

    areas: list[CanonicalArea] = []

    with reader:
        try:
            for shape_record in reader.iterShapeRecords():
                raw_fields = shape_record.record.as_dict()

                source_fields = {str(key): _json_safe(value) for key, value in raw_fields.items()}

                source_id = source_fields.get("ID")

                if not isinstance(
                    source_id,
                    int,
                ):
                    raise CanonicalIngestionError("Decoded source ID is not an integer.")

                _validate_publisher_fields(
                    source_id,
                    source_fields,
                )

                geometry = shapely_shape(shape_record.shape.__geo_interface__)

                (
                    canonical_geometry,
                    transformation,
                ) = canonicalise_source_geometry(
                    source_id,
                    geometry,
                )

                areas.append(
                    CanonicalArea(
                        source_id=source_id,
                        source_fields=(source_fields),
                        geometry_wkb=(_wkb_bytes(canonical_geometry)),
                        transformation=(transformation),
                    )
                )

        except UnicodeDecodeError as error:
            raise CanonicalIngestionError("DBF content is not strict UTF-8.") from error

    areas.sort(key=lambda item: item.source_id)

    if len(areas) != EXPECTED_RECORD_COUNT:
        raise CanonicalIngestionError("Canonical record count does not match the source contract.")

    source_ids = [area.source_id for area in areas]

    if len(source_ids) != len(set(source_ids)):
        raise CanonicalIngestionError("Canonical source IDs are not unique.")

    if frozenset(source_ids) != frozenset(
        range(
            1,
            EXPECTED_RECORD_COUNT + 1,
        )
    ):
        raise CanonicalIngestionError("Canonical source ID set does not match the reviewed source.")

    transformed_ids = frozenset(area.source_id for area in areas if area.transformation is not None)

    if transformed_ids != APPROVED_REPAIR_IDS:
        raise CanonicalIngestionError("Canonical transformation set does not match ADR 0004.")

    return CanonicalSnapshot(
        source_sha256=digest,
        source_url=(OFWAT_WATER_SUPPLY_V1_5.source_url),
        source_bytes=(OFWAT_WATER_SUPPLY_V1_5.expected_bytes),
        retrieved_at=(_parse_retrieved_at(manifest)),
        publisher=(OFWAT_WATER_SUPPLY_V1_5.publisher),
        distributor=(OFWAT_WATER_SUPPLY_V1_5.distributor),
        licence_name=(OFWAT_WATER_SUPPLY_V1_5.licence_name),
        licence_version=None,
        licence_url=LICENCE_URL,
        attribution=(SOURCE_PROVENANCE_STATEMENT),
        transformation_version=(TRANSFORMATION_VERSION),
        areas=tuple(areas),
    )


SNAPSHOT_INSERT = text("""
    INSERT INTO watergeo.water_supply_snapshot (
        source_sha256,
        source_url,
        source_bytes,
        retrieved_at,
        publisher,
        distributor,
        licence_name,
        licence_version,
        licence_url,
        attribution,
        transformation_version
    )
    VALUES (
        :source_sha256,
        :source_url,
        :source_bytes,
        :retrieved_at,
        :publisher,
        :distributor,
        :licence_name,
        :licence_version,
        :licence_url,
        :attribution,
        :transformation_version
    )
    ON CONFLICT (
        source_sha256,
        transformation_version
    )
    DO NOTHING
    RETURNING id
""")


AREA_INSERT = text("""
    INSERT INTO watergeo.water_supply_area (
        snapshot_id,
        source_id,
        source_fields,
        geom
    )
    VALUES (
        :snapshot_id,
        :source_id,
        CAST(:source_fields AS jsonb),
        public.ST_GeomFromWKB(
            :geometry_wkb,
            27700
        )
    )
""")


TRANSFORMATION_INSERT = text("""
    INSERT INTO watergeo.water_supply_area_transformation (
        snapshot_id,
        source_id,
        transformation_id,
        method,
        keep_collapsed,
        shapely_version,
        geos_version,
        invalid_reason,
        source_decoded_wkb_sha256,
        canonical_wkb_sha256,
        review_status,
        review_reason,
        review_reference,
        details
    )
    VALUES (
        :snapshot_id,
        :source_id,
        :transformation_id,
        :method,
        :keep_collapsed,
        :shapely_version,
        :geos_version,
        :invalid_reason,
        :source_decoded_wkb_sha256,
        :canonical_wkb_sha256,
        :review_status,
        :review_reason,
        :review_reference,
        CAST(:details AS jsonb)
    )
""")


def _snapshot_parameters(
    snapshot: CanonicalSnapshot,
) -> dict[str, Any]:
    return {
        "source_sha256": snapshot.source_sha256,
        "source_url": snapshot.source_url,
        "source_bytes": snapshot.source_bytes,
        "retrieved_at": snapshot.retrieved_at,
        "publisher": snapshot.publisher,
        "distributor": snapshot.distributor,
        "licence_name": snapshot.licence_name,
        "licence_version": snapshot.licence_version,
        "licence_url": snapshot.licence_url,
        "attribution": snapshot.attribution,
        "transformation_version": (snapshot.transformation_version),
    }


def _validate_snapshot_contract(
    snapshot: CanonicalSnapshot,
) -> None:
    if snapshot.source_sha256 != OFWAT_WATER_SUPPLY_V1_5.expected_sha256:
        raise CanonicalIngestionError("Canonical snapshot has an unexpected source SHA-256.")

    if snapshot.source_url != OFWAT_WATER_SUPPLY_V1_5.source_url:
        raise CanonicalIngestionError("Canonical snapshot has an unexpected source URL.")

    if snapshot.source_bytes != OFWAT_WATER_SUPPLY_V1_5.expected_bytes:
        raise CanonicalIngestionError("Canonical snapshot has an unexpected source byte count.")

    if snapshot.transformation_version != TRANSFORMATION_VERSION:
        raise CanonicalIngestionError(
            "Canonical snapshot has an unexpected transformation version."
        )

    if len(snapshot.areas) != EXPECTED_RECORD_COUNT:
        raise CanonicalIngestionError("Canonical snapshot does not contain exactly 1,141 areas.")

    ids = tuple(area.source_id for area in snapshot.areas)

    if ids != tuple(
        range(
            1,
            EXPECTED_RECORD_COUNT + 1,
        )
    ):
        raise CanonicalIngestionError(
            "Canonical source IDs are not exactly the reviewed 1..1141 sequence."
        )

    transformed_ids = frozenset(
        area.source_id for area in snapshot.areas if area.transformation is not None
    )

    if transformed_ids != APPROVED_REPAIR_IDS:
        raise CanonicalIngestionError(
            "Canonical snapshot does not contain exactly the five approved transformations."
        )

    for area in snapshot.areas:
        provenance = area.transformation

        if provenance is None:
            continue

        contract = APPROVED_GEOMETRY_CONTRACTS[area.source_id]

        canonical_hash = hashlib.sha256(area.geometry_wkb).hexdigest()

        if canonical_hash != contract.canonical_wkb_sha256:
            raise CanonicalIngestionError(
                f"Canonical area {area.source_id} does not match its approved WKB hash."
            )

        expected_provenance = {
            "source_id": area.source_id,
            "transformation_id": TRANSFORMATION_VERSION,
            "method": TRANSFORMATION_METHOD,
            "keep_collapsed": (TRANSFORMATION_KEEP_COLLAPSED),
            "shapely_version": (EXPECTED_SHAPELY_VERSION),
            "geos_version": (EXPECTED_GEOS_VERSION),
            "source_decoded_wkb_sha256": (contract.source_wkb_sha256),
            "canonical_wkb_sha256": (contract.canonical_wkb_sha256),
            "review_status": "approved",
            "review_reference": REVIEW_REFERENCE,
        }

        for key, expected_value in expected_provenance.items():
            if getattr(provenance, key) != expected_value:
                raise CanonicalIngestionError(
                    f"Canonical area {area.source_id} "
                    "has inconsistent transformation "
                    f"provenance: {key}."
                )


def _existing_snapshot_id(
    connection: Connection,
    snapshot: CanonicalSnapshot,
) -> UUID:
    row = (
        connection.execute(
            text("""
            SELECT
                id,
                source_url,
                source_bytes,
                retrieved_at,
                publisher,
                distributor,
                licence_name,
                licence_version,
                licence_url,
                attribution
            FROM watergeo.water_supply_snapshot
            WHERE source_sha256 = :source_sha256
              AND transformation_version =
                  :transformation_version
        """),
            {
                "source_sha256": (snapshot.source_sha256),
                "transformation_version": (snapshot.transformation_version),
            },
        )
        .mappings()
        .one()
    )

    expected = {
        "source_url": snapshot.source_url,
        "source_bytes": snapshot.source_bytes,
        "retrieved_at": snapshot.retrieved_at,
        "publisher": snapshot.publisher,
        "distributor": snapshot.distributor,
        "licence_name": snapshot.licence_name,
        "licence_version": snapshot.licence_version,
        "licence_url": snapshot.licence_url,
        "attribution": snapshot.attribution,
    }

    for key, expected_value in expected.items():
        if row[key] != expected_value:
            raise CanonicalIngestionError(f"Existing snapshot provenance does not match: {key}.")

    snapshot_id = row["id"]

    if not isinstance(
        snapshot_id,
        UUID,
    ):
        raise CanonicalIngestionError("Existing snapshot ID is not a UUID.")

    return snapshot_id


def _verify_loaded_snapshot(
    connection: Connection,
    snapshot_id: UUID,
    snapshot: CanonicalSnapshot,
) -> tuple[int, int]:
    area_rows = (
        connection.execute(
            text("""
                SELECT
                    source_id,
                    source_fields,
                    public.ST_AsBinary(
                        geom,
                        'NDR'
                    ) AS geometry_wkb
                FROM watergeo.water_supply_area
                WHERE snapshot_id = :snapshot_id
                ORDER BY source_id
            """),
            {
                "snapshot_id": snapshot_id,
            },
        )
        .mappings()
        .all()
    )

    expected_ids = tuple(area.source_id for area in snapshot.areas)

    stored_ids = tuple(int(row["source_id"]) for row in area_rows)

    if stored_ids != expected_ids:
        raise CanonicalIngestionError("Loaded source ID set does not match the canonical snapshot.")

    expected_areas = {area.source_id: area for area in snapshot.areas}

    for row in area_rows:
        source_id = int(row["source_id"])

        expected_area = expected_areas[source_id]
        if row["source_fields"] != expected_area.source_fields:
            raise CanonicalIngestionError(
                f"Loaded source fields for {source_id} do not match the canonical snapshot."
            )

        stored_wkb = bytes(row["geometry_wkb"])

        if stored_wkb != expected_area.geometry_wkb:
            raise CanonicalIngestionError(
                f"Loaded geometry for {source_id} does not match the canonical snapshot."
            )

    bad_geometry_count = int(
        connection.execute(
            text("""
                SELECT count(*)
                FROM watergeo.water_supply_area
                WHERE snapshot_id = :snapshot_id
                  AND (
                      public.GeometryType(geom)
                          <> 'MULTIPOLYGON'
                      OR public.ST_SRID(geom)
                          <> 27700
                      OR public.ST_NDims(geom)
                          <> 2
                      OR public.ST_IsEmpty(geom)
                      OR NOT public.ST_IsValid(
                          geom,
                          0
                      )
                  )
            """),
            {
                "snapshot_id": snapshot_id,
            },
        ).scalar_one()
    )

    if bad_geometry_count != 0:
        raise CanonicalIngestionError("Loaded snapshot contains unacceptable canonical geometry.")

    transformation_rows = (
        connection.execute(
            text("""
                SELECT
                    source_id,
                    transformation_id,
                    method,
                    keep_collapsed,
                    shapely_version,
                    geos_version,
                    invalid_reason,
                    source_decoded_wkb_sha256,
                    canonical_wkb_sha256,
                    review_status,
                    review_reason,
                    review_reference,
                    details
                FROM
                    watergeo
                    .water_supply_area_transformation
                WHERE snapshot_id = :snapshot_id
                ORDER BY source_id
            """),
            {
                "snapshot_id": snapshot_id,
            },
        )
        .mappings()
        .all()
    )

    expected_transformations: dict[
        int,
        TransformationProvenance,
    ] = {}

    for area in snapshot.areas:
        if area.transformation is not None:
            expected_transformations[area.source_id] = area.transformation

    stored_transformation_ids = tuple(int(row["source_id"]) for row in transformation_rows)

    if stored_transformation_ids != tuple(expected_transformations):
        raise CanonicalIngestionError(
            "Loaded transformation IDs do not match the canonical snapshot."
        )

    for row in transformation_rows:
        source_id = int(row["source_id"])

        expected_transformation = expected_transformations[source_id]
        expected_values = {
            "transformation_id": (expected_transformation.transformation_id),
            "method": expected_transformation.method,
            "keep_collapsed": (expected_transformation.keep_collapsed),
            "shapely_version": (expected_transformation.shapely_version),
            "geos_version": (expected_transformation.geos_version),
            "invalid_reason": (expected_transformation.invalid_reason),
            "source_decoded_wkb_sha256": (expected_transformation.source_decoded_wkb_sha256),
            "canonical_wkb_sha256": (expected_transformation.canonical_wkb_sha256),
            "review_status": (expected_transformation.review_status),
            "review_reason": (expected_transformation.review_reason),
            "review_reference": (expected_transformation.review_reference),
            "details": expected_transformation.details,
        }

        for key, expected_value in expected_values.items():
            if row[key] != expected_value:
                raise CanonicalIngestionError(
                    "Loaded transformation provenance "
                    f"does not match for source "
                    f"{source_id}: {key}."
                )

    return (
        len(area_rows),
        len(transformation_rows),
    )


def load_canonical_snapshot(
    engine: Engine,
    snapshot: CanonicalSnapshot,
) -> LoadResult:
    """Atomically load or verify the exact canonical snapshot."""

    _validate_snapshot_contract(snapshot)

    with engine.begin() as connection:
        inserted = connection.execute(
            SNAPSHOT_INSERT,
            _snapshot_parameters(snapshot),
        ).scalar_one_or_none()

        if inserted is None:
            snapshot_id = _existing_snapshot_id(
                connection,
                snapshot,
            )

            (
                area_count,
                transformed_count,
            ) = _verify_loaded_snapshot(
                connection,
                snapshot_id,
                snapshot,
            )

            return LoadResult(
                snapshot_id=snapshot_id,
                status="existing",
                area_count=area_count,
                transformed_count=(transformed_count),
            )

        if not isinstance(
            inserted,
            UUID,
        ):
            raise CanonicalIngestionError("Inserted snapshot ID is not a UUID.")

        snapshot_id = inserted

        area_parameters = [
            {
                "snapshot_id": snapshot_id,
                "source_id": area.source_id,
                "source_fields": json.dumps(
                    area.source_fields,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "geometry_wkb": (area.geometry_wkb),
            }
            for area in snapshot.areas
        ]

        connection.execute(
            AREA_INSERT,
            area_parameters,
        )

        transformations = [
            area.transformation for area in snapshot.areas if area.transformation is not None
        ]

        if len(transformations) != len(APPROVED_REPAIR_IDS):
            raise CanonicalIngestionError(
                "Canonical transformation count changed before database insertion."
            )

        transformation_parameters = []

        for item in transformations:
            if item is None:
                raise CanonicalIngestionError("Transformation provenance unexpectedly disappeared.")

            transformation_parameters.append(
                {
                    "snapshot_id": snapshot_id,
                    "source_id": item.source_id,
                    "transformation_id": (item.transformation_id),
                    "method": item.method,
                    "keep_collapsed": (item.keep_collapsed),
                    "shapely_version": (item.shapely_version),
                    "geos_version": (item.geos_version),
                    "invalid_reason": (item.invalid_reason),
                    "source_decoded_wkb_sha256": (item.source_decoded_wkb_sha256),
                    "canonical_wkb_sha256": (item.canonical_wkb_sha256),
                    "review_status": (item.review_status),
                    "review_reason": (item.review_reason),
                    "review_reference": (item.review_reference),
                    "details": json.dumps(
                        item.details,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )

        connection.execute(
            TRANSFORMATION_INSERT,
            transformation_parameters,
        )

        (
            area_count,
            transformed_count,
        ) = _verify_loaded_snapshot(
            connection,
            snapshot_id,
            snapshot,
        )

    return LoadResult(
        snapshot_id=snapshot_id,
        status="inserted",
        area_count=area_count,
        transformed_count=(transformed_count),
    )


def load_reviewed_water_supply(
    engine: Engine,
    *,
    raw_root: Path = Path("data/raw/ofwat/water-supply"),
) -> LoadResult:
    """Decode, transform and atomically load the reviewed release."""

    snapshot = decode_reviewed_water_supply(raw_root=raw_root)

    return load_canonical_snapshot(
        engine,
        snapshot,
    )
