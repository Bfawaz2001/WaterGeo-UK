"""Strict normalization of the reviewed EA Water Quality Explorer sampling-point contract."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

ROOT = "https://environment.data.gov.uk/water-quality"
SAMPLING_POINT_ROOT = ROOT + "/sampling-point/"
CONTEXT = ROOT + "/context/wqa_samplingpoint_context.json-ld"
CRS_4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"
API_VERSION = "1"
LICENCE = "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
VERSION = "ea-water-quality-sampling-points-v1"

ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:/ -]{1,256}$")
POINT_WKT = re.compile(
    r"^POINT\("
    r"([-+]?(?:\d+(?:\.\d+)?|\.\d+)) "
    r"([-+]?(?:\d+(?:\.\d+)?|\.\d+))"
    r"\) <http://www\.opengis\.net/def/crs/EPSG/0/4326>$"
)


class WaterQualityError(ValueError):
    """A source contract, completeness or evidence check failed."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WaterQualityError("Duplicate JSON member")
        result[key] = value
    return result


def decode(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WaterQualityError("Malformed JSON response") from error
    if not isinstance(value, dict):
        raise WaterQualityError("Expected JSON object")
    try:
        encoded(value)
    except (ValueError, RecursionError) as error:
        raise WaterQualityError("Invalid JSON values") from error
    return value


def string(value: Any, field: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise WaterQualityError(f"Invalid {field}")
    return value


def optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return string(value, field)


def finite_number(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise WaterQualityError(f"Invalid {field}") from error
    if not math.isfinite(result):
        raise WaterQualityError(f"Invalid {field}")
    return result


def notation_from_id(value: Any) -> str:
    uri = string(value, "sampling point id")
    if not uri.startswith(SAMPLING_POINT_ROOT):
        raise WaterQualityError("Unexpected sampling point identity")
    notation = uri[len(SAMPLING_POINT_ROOT) :]
    if not ID_PATTERN.fullmatch(notation):
        raise WaterQualityError("Unexpected sampling point identity")
    return notation


def concept(value: Any, field: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise WaterQualityError(f"Invalid {field}")
    notation = string(value.get("notation"), f"{field} notation", max_length=256)
    label = string(value.get("prefLabel"), f"{field} label")
    return {"notation": notation, "pref_label": label}


def point_geometry(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise WaterQualityError("Invalid sampling point geometry")
    if value.get("@type") != "geo:Geometry":
        raise WaterQualityError("Unexpected geometry type")
    raw = string(value.get("asWKT"), "sampling point WKT")
    match = POINT_WKT.fullmatch(raw)
    if not match:
        raise WaterQualityError("Unsupported sampling point geometry")
    longitude = finite_number(match.group(1), "longitude")
    latitude = finite_number(match.group(2), "latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise WaterQualityError("Coordinates outside WGS84 range")
    return latitude, longitude


@dataclass(frozen=True)
class Normalized:
    sampling_points: list[dict[str, Any]]
    sha256: str

    @property
    def counts(self) -> dict[str, int]:
        located = sum(row["latitude"] is not None for row in self.sampling_points)
        return {
            "sampling_point_count": len(self.sampling_points),
            "sampling_point_with_location_count": located,
            "sampling_point_without_location_count": len(self.sampling_points) - located,
        }


def normalize(records: list[dict[str, Any]]) -> Normalized:
    points: dict[str, dict[str, Any]] = {}

    for raw in records:
        if not isinstance(raw, dict):
            raise WaterQualityError("Invalid sampling point record")

        notation = notation_from_id(raw.get("id"))
        published_notation = raw.get("notation")
        if (
            published_notation is not None
            and string(
                published_notation,
                "sampling point notation",
                max_length=256,
            )
            != notation
        ):
            raise WaterQualityError("Inconsistent sampling point notation")

        if notation in points:
            raise WaterQualityError("Duplicate sampling point identity")

        types = raw.get("@type")
        if types is not None and (
            not isinstance(types, list)
            or any(not isinstance(item, str) for item in types)
            or "sosa:FeatureOfInterest" not in types
            or "geo:Feature" not in types
        ):
            raise WaterQualityError("Unexpected sampling point resource type")

        alt_label = string(raw.get("altLabel"), "sampling point altLabel")
        pref_label = optional_string(raw.get("prefLabel"), "sampling point prefLabel")

        expected_observations = SAMPLING_POINT_ROOT + notation + "/observation"
        has_observations = raw.get("hasObservations")
        if has_observations is not None and has_observations != expected_observations:
            raise WaterQualityError("Unexpected observations relationship")

        latitude, longitude = point_geometry(raw.get("geometry"))

        points[notation] = {
            "sampling_point_id": notation,
            "source_uri": raw["id"],
            "alt_label": alt_label,
            "pref_label": pref_label,
            "latitude": latitude,
            "longitude": longitude,
            "status": concept(raw.get("samplingPointStatus"), "sampling point status"),
            "sampling_point_type": concept(raw.get("samplingPointType"), "sampling point type"),
            "region": concept(raw.get("region"), "sampling point region"),
            "area": concept(raw.get("area"), "sampling point area"),
            "sub_area": concept(raw.get("subArea"), "sampling point subArea"),
            "source_fields": raw,
        }

    if not points:
        raise WaterQualityError("Empty sampling point snapshot")

    normalized = [points[key] for key in sorted(points)]
    return Normalized(
        sampling_points=normalized,
        sha256=digest(
            {
                "normalization_version": VERSION,
                "sampling_points": normalized,
            }
        ),
    )
