"""Diagnostic repair assessment for invalid Ofwat boundary geometry.

This module evaluates reproducible candidate transformations. It does not approve
a repair, alter the raw source, or make any geometry eligible for canonical loading.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import shapefile
import shapely
from shapely import make_valid, to_wkb
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity

from watergeo.ingestion.ofwat_boundaries import OFWAT_WATER_SUPPLY_V1_5
from watergeo.ingestion.ofwat_boundary_validation import (
    EXPECTED_INVALID_IDS,
    validate_boundary_archive,
)

ASSESSMENT_VERSION = "ofwat-water-supply-v1_5-repair-assessment-v1"
ASSESSMENT_STATUS = "diagnostic_only_not_approved"
MAX_DIFFERENCE_PROBES = 20

METHODS = (
    ("linework", "linework", True),
    ("structure_keep", "structure", True),
    ("structure_drop", "structure", False),
)


class BoundaryRepairAssessmentError(RuntimeError):
    """Raised when a repair assessment cannot be reproduced safely."""


@dataclass(frozen=True, slots=True)
class OriginalGeometryEvidence:
    geometry_type: str
    valid: bool
    invalid_reason: str
    empty: bool
    area_untrusted_m2: float
    bounds: tuple[float, float, float, float]
    wkb_sha256: str


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    candidate_id: str
    method: str
    keep_collapsed: bool
    geometry_type: str
    valid: bool
    empty: bool
    polygonal: bool
    area_m2: float
    part_count: int
    has_lower_dimension_parts: bool
    bounds: tuple[float, float, float, float]
    wkb_sha256: str
    meets_geometry_checks: bool


@dataclass(frozen=True, slots=True)
class DifferenceProbe:
    x: float
    y: float
    left_covers: bool
    right_covers: bool


@dataclass(frozen=True, slots=True)
class CandidateComparison:
    left_candidate: str
    right_candidate: str
    topologically_equal: bool
    coordinates_identical: bool
    symmetric_difference_area_m2: float
    hausdorff_distance_m: float
    difference_probe_points: tuple[DifferenceProbe, ...]


@dataclass(frozen=True, slots=True)
class FeatureRepairAssessment:
    source_id: int
    original: OriginalGeometryEvidence
    candidates: tuple[CandidateEvidence, ...]
    comparisons: tuple[CandidateComparison, ...]


@dataclass(frozen=True, slots=True)
class BoundaryRepairAssessmentReport:
    assessment_version: str
    assessment_status: str
    dataset: str
    release: str
    source_sha256: str
    target_source_ids: tuple[int, ...]
    shapely_version: str
    geos_version: str
    geometry_hash_encoding: str
    features: tuple[FeatureRepairAssessment, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _geometry_hash(geometry: Any) -> str:
    raw = to_wkb(
        geometry,
        hex=False,
        byte_order=1,
        include_srid=False,
    )

    if not isinstance(raw, bytes):
        raise BoundaryRepairAssessmentError(
            "Shapely did not return binary WKB for geometry hashing."
        )

    return hashlib.sha256(raw).hexdigest()


def _bounds(
    geometry: Any,
) -> tuple[float, float, float, float]:
    values = tuple(float(value) for value in geometry.bounds)

    if len(values) != 4:
        raise BoundaryRepairAssessmentError("Geometry did not produce four planar bounds values.")

    return (
        values[0],
        values[1],
        values[2],
        values[3],
    )


def _leaf_geometries(geometry: Any) -> list[Any]:
    children = getattr(geometry, "geoms", None)

    if children is None:
        return [geometry]

    leaves: list[Any] = []

    for child in children:
        leaves.extend(_leaf_geometries(child))

    return leaves


def _part_count(geometry: Any) -> int:
    if geometry.is_empty:
        return 0

    children = getattr(geometry, "geoms", None)

    if children is None:
        return 1

    return len(children)


def _has_lower_dimension_parts(geometry: Any) -> bool:
    return any(part.geom_type not in {"Polygon"} for part in _leaf_geometries(geometry))


def _candidate(
    original: Any,
    *,
    candidate_id: str,
    method: str,
    keep_collapsed: bool,
) -> tuple[CandidateEvidence, Any]:
    candidate = make_valid(
        original,
        method=method,
        keep_collapsed=keep_collapsed,
    )

    polygonal = candidate.geom_type in {
        "Polygon",
        "MultiPolygon",
    }

    valid = bool(candidate.is_valid)
    empty = bool(candidate.is_empty)
    lower_dimension = _has_lower_dimension_parts(candidate)

    evidence = CandidateEvidence(
        candidate_id=candidate_id,
        method=method,
        keep_collapsed=keep_collapsed,
        geometry_type=str(candidate.geom_type),
        valid=valid,
        empty=empty,
        polygonal=polygonal,
        area_m2=float(candidate.area),
        part_count=_part_count(candidate),
        has_lower_dimension_parts=lower_dimension,
        bounds=_bounds(candidate),
        wkb_sha256=_geometry_hash(candidate),
        meets_geometry_checks=(valid and not empty and polygonal and not lower_dimension),
    )

    return evidence, candidate


def _difference_parts(geometry: Any) -> list[Any]:
    if geometry.is_empty:
        return []

    children = getattr(geometry, "geoms", None)

    if children is None:
        return [geometry]

    parts = list(children)

    return sorted(
        parts,
        key=lambda item: (
            tuple(float(value) for value in item.bounds),
            float(item.area),
            str(item.geom_type),
        ),
    )


def _compare_candidates(
    left_id: str,
    left: Any,
    right_id: str,
    right: Any,
) -> CandidateComparison:
    left_hash = _geometry_hash(left)
    right_hash = _geometry_hash(right)

    coordinates_identical = left_hash == right_hash

    if coordinates_identical:
        return CandidateComparison(
            left_candidate=left_id,
            right_candidate=right_id,
            topologically_equal=True,
            coordinates_identical=True,
            symmetric_difference_area_m2=0.0,
            hausdorff_distance_m=0.0,
            difference_probe_points=(),
        )

    topologically_equal = bool(left.equals(right))

    if topologically_equal:
        return CandidateComparison(
            left_candidate=left_id,
            right_candidate=right_id,
            topologically_equal=True,
            coordinates_identical=False,
            symmetric_difference_area_m2=0.0,
            hausdorff_distance_m=0.0,
            difference_probe_points=(),
        )

    difference = left.symmetric_difference(right)

    probes: list[DifferenceProbe] = []

    for part in _difference_parts(difference)[:MAX_DIFFERENCE_PROBES]:
        if part.is_empty:
            continue

        probe = part.representative_point()

        probes.append(
            DifferenceProbe(
                x=float(probe.x),
                y=float(probe.y),
                left_covers=bool(left.covers(probe)),
                right_covers=bool(right.covers(probe)),
            )
        )

    return CandidateComparison(
        left_candidate=left_id,
        right_candidate=right_id,
        topologically_equal=False,
        coordinates_identical=False,
        symmetric_difference_area_m2=float(difference.area),
        hausdorff_distance_m=float(left.hausdorff_distance(right)),
        difference_probe_points=tuple(probes),
    )


def assess_invalid_geometry(
    source_id: int,
    geometry: Any,
) -> FeatureRepairAssessment:
    """Assess candidate repairs for one invalid source geometry."""

    if geometry.is_empty:
        raise BoundaryRepairAssessmentError(f"Source geometry {source_id} is empty.")

    if geometry.is_valid:
        raise BoundaryRepairAssessmentError(f"Source geometry {source_id} is already valid.")

    original = OriginalGeometryEvidence(
        geometry_type=str(geometry.geom_type),
        valid=False,
        invalid_reason=explain_validity(geometry),
        empty=False,
        area_untrusted_m2=float(geometry.area),
        bounds=_bounds(geometry),
        wkb_sha256=_geometry_hash(geometry),
    )

    evidence: list[CandidateEvidence] = []
    candidate_geometries: dict[str, Any] = {}

    for candidate_id, method, keep_collapsed in METHODS:
        candidate_evidence, candidate_geometry = _candidate(
            geometry,
            candidate_id=candidate_id,
            method=method,
            keep_collapsed=keep_collapsed,
        )

        evidence.append(candidate_evidence)

        candidate_geometries[candidate_id] = candidate_geometry

    comparisons: list[CandidateComparison] = []

    for left, right in combinations(
        candidate_geometries,
        2,
    ):
        comparisons.append(
            _compare_candidates(
                left,
                candidate_geometries[left],
                right,
                candidate_geometries[right],
            )
        )

    return FeatureRepairAssessment(
        source_id=source_id,
        original=original,
        candidates=tuple(evidence),
        comparisons=tuple(comparisons),
    )


def _read_target_geometries(
    archive_path: Path,
    *,
    target_ids: frozenset[int],
) -> dict[int, Any]:
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
        raise BoundaryRepairAssessmentError(
            "Verified source archive could not be opened for repair assessment."
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
        raise BoundaryRepairAssessmentError(
            "Verified source could not be decoded for repair assessment."
        ) from error

    geometries: dict[int, Any] = {}

    with reader:
        try:
            for shape_record in reader.iterShapeRecords():
                source_id_raw = shape_record.record["ID"]

                if not isinstance(
                    source_id_raw,
                    int,
                ):
                    raise BoundaryRepairAssessmentError("Source ID is not an integer.")

                if source_id_raw not in target_ids:
                    continue

                geometries[source_id_raw] = shapely_shape(shape_record.shape.__geo_interface__)

        except UnicodeDecodeError as error:
            raise BoundaryRepairAssessmentError("DBF content is not strict UTF-8.") from error

    if frozenset(geometries) != target_ids:
        raise BoundaryRepairAssessmentError(
            "Repair assessment target IDs do not match the verified source."
        )

    return geometries


def build_reviewed_repair_assessment(
    *,
    raw_root: Path = Path("data/raw/ofwat/water-supply"),
) -> BoundaryRepairAssessmentReport:
    """Build diagnostic evidence for the five reviewed invalid features."""

    archive_path = raw_root / (f"{OFWAT_WATER_SUPPLY_V1_5.expected_sha256}.zip")

    validation = validate_boundary_archive(archive_path)

    invalid_ids = frozenset(item.source_id for item in validation.invalid_geometries)

    if invalid_ids != EXPECTED_INVALID_IDS:
        raise BoundaryRepairAssessmentError(
            "Validated invalid geometry set does not match the reviewed release."
        )

    geometries = _read_target_geometries(
        archive_path,
        target_ids=invalid_ids,
    )

    features = tuple(
        assess_invalid_geometry(
            source_id,
            geometries[source_id],
        )
        for source_id in sorted(geometries)
    )

    return BoundaryRepairAssessmentReport(
        assessment_version=ASSESSMENT_VERSION,
        assessment_status=ASSESSMENT_STATUS,
        dataset=validation.dataset,
        release=validation.release,
        source_sha256=validation.source_sha256,
        target_source_ids=tuple(sorted(invalid_ids)),
        shapely_version=shapely.__version__,
        geos_version=shapely.geos_version_string,
        geometry_hash_encoding=(
            "Little-endian WKB from decoded Shapely geometry, without normalisation"
        ),
        features=features,
    )


def write_repair_assessment(
    report: BoundaryRepairAssessmentReport,
    *,
    output_root: Path = Path("data/validation/ofwat/water-supply"),
) -> Path:
    """Write deterministic diagnostic evidence atomically."""

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = output_root / (f"{report.source_sha256}.repair-assessment.json")

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
        prefix=".repair-assessment-",
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
        temporary.unlink(missing_ok=True)
        raise

    return destination
