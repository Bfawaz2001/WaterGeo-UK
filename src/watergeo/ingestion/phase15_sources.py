"""Strict normalization for Phase 15 national source products."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shapely import hausdorff_distance, make_valid
from shapely.geometry import mapping, shape
from shapely.validation import explain_validity

EA_LICENCE = "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
EA_PUBLISHER = "Environment Agency"
FLOOD_ROOT = "https://environment.data.gov.uk/flood-monitoring"
BATHING_ROOT = "https://environment.data.gov.uk/doc/bathing-water.json"
OFWAT_WCPR_URL = (
    "https://www.ofwat.gov.uk/publication/"
    "data-for-the-water-company-performance-report-2024-25-open-data-friendly-machine-readable-format/"
)
OFWAT_PR24_URL = "https://www.ofwat.gov.uk/publication/historical-performance-trends-for-pr24-v6-0/"
VERSION = "phase15-national-products-v1"
BOUNDARY_CROSSWALK_VERSION = "ofwat-to-water-supply-v1"
FLOOD_GEOMETRY_POLICY = "ea-flood-area-structure-v1"
IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class Phase15SourceError(ValueError):
    """A reviewed Phase 15 publisher contract was not met."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def decode(body: bytes) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise Phase15SourceError("Duplicate JSON member")
            result[key] = value
        return result

    try:
        value = json.loads(body, object_pairs_hook=pairs)
        encoded(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Phase15SourceError("Malformed source JSON") from error
    if not isinstance(value, dict):
        raise Phase15SourceError("Expected source JSON object")
    return value


def text(value: Any, field: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Phase15SourceError(f"Invalid {field}")
    return value.strip()


def number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Phase15SourceError(f"Invalid {field}")
    result = float(value)
    if not math.isfinite(result):
        raise Phase15SourceError(f"Invalid {field}")
    return result


def timestamp(value: Any, field: str) -> str:
    raw = text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise Phase15SourceError(f"Invalid {field}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _ea(payload: dict[str, Any]) -> list[dict[str, Any]]:
    meta = payload.get("meta")
    items = payload.get("items")
    if (
        not isinstance(meta, dict)
        or meta.get("publisher") != EA_PUBLISHER
        or meta.get("licence") != EA_LICENCE
        or meta.get("version") != "0.9"
        or not isinstance(items, list)
    ):
        raise Phase15SourceError("Environment Agency source contract changed")
    if not all(isinstance(item, dict) for item in items):
        raise Phase15SourceError("Invalid Environment Agency items")
    return items


@dataclass(frozen=True)
class NormalizedProduct:
    source: str
    entities: list[dict[str, Any]]
    secondary: list[dict[str, Any]]
    skipped_count: int = 0

    @property
    def sha256(self) -> str:
        return digest(
            {
                "version": VERSION,
                "source": self.source,
                "entities": self.entities,
                "secondary": self.secondary,
                "skipped_count": self.skipped_count,
            }
        )


def normalize_rainfall(
    stations_payload: dict[str, Any], readings_payload: dict[str, Any]
) -> NormalizedProduct:
    stations_raw = _ea(stations_payload)
    readings_raw = _ea(readings_payload)
    readings: dict[str, dict[str, Any]] = {}
    for raw in readings_raw:
        measure = raw.get("measure")
        if not isinstance(measure, dict):
            raise Phase15SourceError("Invalid rainfall reading measure")
        measure_uri = text(measure.get("@id"), "rainfall reading measure")
        if measure_uri in readings:
            raise Phase15SourceError("Duplicate latest rainfall measure")
        raw_value = raw.get("value")
        value = None if raw_value is None else number(raw_value, "rainfall value")
        if value is not None and value < 0:
            raise Phase15SourceError("Negative rainfall value")
        readings[measure_uri] = {
            "measure_uri": measure_uri,
            "observed_at": timestamp(raw.get("dateTime"), "rainfall observation timestamp"),
            "value_mm": value,
            "source_fields": raw,
        }
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    used_measures: set[str] = set()
    skipped_stations = 0
    for raw in stations_raw:
        if (
            raw.get("@id")
            in {
                f"{FLOOD_ROOT}/id/stations/",
                "http://environment.data.gov.uk/flood-monitoring/id/stations/",
            }
            and raw.get("notation") == ""
            and raw.get("stationReference") == ""
        ):
            skipped_stations += 1
            continue
        station_id = text(raw.get("notation"), "rainfall station identity", 160)
        if not IDENTITY.fullmatch(station_id) or station_id in seen:
            raise Phase15SourceError("Invalid or duplicate rainfall station identity")
        seen.add(station_id)
        raw_latitude, raw_longitude = raw.get("lat"), raw.get("long")
        if (raw_latitude is None) != (raw_longitude is None):
            raise Phase15SourceError("Incomplete rainfall station location")
        latitude = None if raw_latitude is None else number(raw_latitude, "rainfall latitude")
        longitude = None if raw_longitude is None else number(raw_longitude, "rainfall longitude")
        if latitude is not None and (
            not 49 <= latitude <= 56 or longitude is None or not -7 <= longitude <= 3
        ):
            raise Phase15SourceError("Rainfall station outside reviewed bounds")
        measures = raw.get("measures")
        if isinstance(measures, dict):
            measures = [measures]
        if not isinstance(measures, list) or not measures:
            raise Phase15SourceError("Rainfall station has no measure")
        station_readings: list[dict[str, Any]] = []
        for measure in measures:
            if not isinstance(measure, dict):
                raise Phase15SourceError("Invalid rainfall measure")
            uri = text(measure.get("@id"), "rainfall measure identity")
            period = measure.get("period")
            unit = measure.get("unitName")
            if (
                measure.get("parameter") != "rainfall"
                or isinstance(period, bool)
                or not isinstance(period, (int, float))
                or period <= 0
                or not isinstance(unit, str)
                or not unit
            ):
                raise Phase15SourceError("Rainfall measure semantics changed")
            if uri in readings:
                used_measures.add(uri)
                station_readings.append(
                    {**readings[uri], "period_seconds": int(period), "unit": unit}
                )
        latest = max(station_readings, key=lambda row: row["observed_at"], default=None)
        label = raw.get("label")
        display_name = (
            label.strip() if isinstance(label, str) and label != "Rainfall station" else None
        )
        entities.append(
            {
                "station_id": station_id,
                "publisher_uri": text(raw.get("@id"), "rainfall station URI"),
                "display_name": display_name,
                "latitude": latitude,
                "longitude": longitude,
                "grid_reference": raw.get("gridReference"),
                "latest_observed_at": latest["observed_at"] if latest else None,
                "latest_value": latest["value_mm"] if latest else None,
                "latest_value_mm": (
                    latest["value_mm"] if latest and latest["unit"] == "mm" else None
                ),
                "latest_unit": latest["unit"] if latest else None,
                "latest_period_seconds": latest["period_seconds"] if latest else None,
                "source_fields": raw,
            }
        )
    if not entities:
        raise Phase15SourceError("Rainfall snapshot is empty")
    entities.sort(key=lambda row: row["station_id"])
    return NormalizedProduct(
        "rainfall",
        entities,
        sorted(readings.values(), key=lambda r: r["measure_uri"]),
        skipped_stations + len(set(readings) - used_measures),
    )


SEVERITIES = {
    1: "severe flood warning",
    2: "flood warning",
    3: "flood alert",
    4: "warning no longer in force",
}


def _parts_and_holes(geometry: Any) -> tuple[int, int]:
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    return len(polygons), sum(len(polygon.interiors) for polygon in polygons)


def _flood_geometry(value: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        original = shape(value)
    except (TypeError, ValueError) as error:
        raise Phase15SourceError("Malformed flood area geometry") from error
    if original.is_empty or original.geom_type not in {"Polygon", "MultiPolygon"}:
        raise Phase15SourceError("Missing or invalid flood area geometry")
    if original.is_valid:
        return value, {"policy": "source-valid", "repaired": False}
    repaired = make_valid(original, method="structure", keep_collapsed=False)
    if (
        repaired.is_empty
        or not repaired.is_valid
        or repaired.geom_type not in {"Polygon", "MultiPolygon"}
        or original.area <= 0
    ):
        raise Phase15SourceError("Flood area geometry repair was not safely polygonal")
    area_change = abs(repaired.area - original.area)
    distance = hausdorff_distance(original, repaired)
    if area_change / original.area > 0.000001 or distance > 0.0001:
        raise Phase15SourceError("Flood area geometry repair exceeded reviewed distortion")
    before_parts, before_holes = _parts_and_holes(original)
    after_parts, after_holes = _parts_and_holes(repaired)
    policy = {
        "policy": FLOOD_GEOMETRY_POLICY,
        "repaired": True,
        "reason": explain_validity(original),
        "source_wkb_sha256": hashlib.sha256(original.wkb).hexdigest(),
        "canonical_wkb_sha256": hashlib.sha256(repaired.wkb).hexdigest(),
        "area_change_square_degrees": area_change,
        "hausdorff_degrees": distance,
        "parts_before": before_parts,
        "parts_after": after_parts,
        "holes_before": before_holes,
        "holes_after": after_holes,
    }
    return mapping(repaired), policy


def normalize_floods(
    warnings_payload: dict[str, Any], areas_payload: dict[str, Any]
) -> NormalizedProduct:
    warnings_raw, areas_raw = _ea(warnings_payload), _ea(areas_payload)
    areas: list[dict[str, Any]] = []
    area_ids: set[str] = set()
    for raw in areas_raw:
        area_id = text(raw.get("notation"), "flood area identity", 160)
        if not IDENTITY.fullmatch(area_id) or area_id in area_ids:
            raise Phase15SourceError("Invalid or duplicate flood area identity")
        area_ids.add(area_id)
        latitude = number(raw.get("lat"), "flood area latitude")
        longitude = number(raw.get("long"), "flood area longitude")
        geometry = raw.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise Phase15SourceError("Missing or invalid flood area geometry")
        canonical_geometry, geometry_policy = _flood_geometry(geometry)
        areas.append(
            {
                "area_id": area_id,
                "publisher_uri": text(raw.get("@id"), "flood area URI"),
                "label": text(raw.get("label"), "flood area label"),
                "description": text(raw.get("description"), "flood area description"),
                "county": text(raw.get("county"), "flood area county"),
                "river_or_sea": raw.get("riverOrSea"),
                "latitude": latitude,
                "longitude": longitude,
                "geometry": canonical_geometry,
                "geometry_policy": geometry_policy,
                "source_fields": raw,
            }
        )
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in warnings_raw:
        area_id = text(raw.get("floodAreaID"), "warning area identity", 160)
        warning_id = text(raw.get("@id"), "warning identity").rsplit("/", 1)[-1]
        severity_level = raw.get("severityLevel")
        severity = text(raw.get("severity"), "warning severity", 64)
        if (
            not IDENTITY.fullmatch(warning_id)
            or warning_id in seen
            or area_id not in area_ids
            or type(severity_level) is not int
            or SEVERITIES.get(severity_level) != severity.lower()
        ):
            raise Phase15SourceError("Invalid flood warning identity, area or severity")
        seen.add(warning_id)
        warnings.append(
            {
                "warning_id": warning_id,
                "area_id": area_id,
                "description": text(raw.get("description"), "warning description"),
                "severity": severity,
                "severity_level": severity_level,
                "message": raw.get("message"),
                "is_tidal": raw.get("isTidal"),
                "time_raised": timestamp(raw.get("timeRaised"), "warning raised timestamp"),
                "time_message_changed": timestamp(
                    raw.get("timeMessageChanged"), "warning message timestamp"
                ),
                "time_severity_changed": timestamp(
                    raw.get("timeSeverityChanged"), "warning severity timestamp"
                ),
                "source_fields": raw,
            }
        )
    areas.sort(key=lambda row: row["area_id"])
    warnings.sort(key=lambda row: row["warning_id"])
    return NormalizedProduct("flood-monitoring", areas, warnings)


def _linked(value: Any, field: str) -> str:
    if isinstance(value, dict):
        value = value.get("_value")
    return text(value, field)


def normalize_bathing(payload: dict[str, Any]) -> NormalizedProduct:
    result = payload.get("result")
    if (
        payload.get("format") != "linked-data-api"
        or payload.get("version") != "0.2"
        or not isinstance(result, dict)
    ):
        raise Phase15SourceError("Bathing-water linked-data contract changed")
    items = result.get("items")
    if not isinstance(items, list) or "next" in result:
        raise Phase15SourceError("Invalid bathing-water items")
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise Phase15SourceError("Invalid bathing-water item")
        identity = text(raw.get("eubwidNotation"), "bathing-water identity", 32)
        point = raw.get("samplingPoint")
        assessment = raw.get("latestComplianceAssessment")
        if identity in seen or not isinstance(point, dict):
            raise Phase15SourceError("Invalid or duplicate bathing-water identity")
        seen.add(identity)
        classification_name: str | None = None
        assessment_year: int | None = None
        if assessment is not None:
            if not isinstance(assessment, dict):
                raise Phase15SourceError("Invalid bathing-water classification")
            classification = assessment.get("complianceClassification")
            if not isinstance(classification, dict):
                raise Phase15SourceError("Missing bathing-water classification")
            assessment_uri = text(assessment.get("_about"), "classification URI")
            year_match = re.search(r"/year/(\d{4})$", assessment_uri)
            if year_match is None:
                raise Phase15SourceError("Ambiguous bathing-water assessment year")
            classification_name = _linked(classification.get("name"), "classification")
            assessment_year = int(year_match.group(1))
        latitude = number(point.get("lat"), "bathing-water latitude")
        longitude = number(point.get("long"), "bathing-water longitude")
        entities.append(
            {
                "bathing_water_id": identity,
                "publisher_uri": text(raw.get("_about"), "bathing-water URI"),
                "name": _linked(raw.get("name"), "bathing-water name"),
                "latitude": latitude,
                "longitude": longitude,
                "classification": classification_name,
                "assessment_year": assessment_year,
                "latest_sample_uri": raw.get("latestSampleAssessment"),
                "latest_risk_prediction": raw.get("latestRiskPrediction"),
                "source_fields": raw,
            }
        )
    if not entities:
        raise Phase15SourceError("Empty bathing-water snapshot")
    entities.sort(key=lambda row: row["bathing_water_id"])
    return NormalizedProduct("bathing-waters", entities, [])


def normalize_company_performance(payload: dict[str, Any]) -> NormalizedProduct:
    if payload.get("publisher") != "Ofwat" or payload.get("licence") != EA_LICENCE:
        raise Phase15SourceError("Ofwat performance metadata changed")
    publication = text(payload.get("publication"), "performance publication")
    crosswalk = payload.get("boundary_crosswalk", {})
    if payload.get("boundary_crosswalk_version") != BOUNDARY_CROSSWALK_VERSION:
        raise Phase15SourceError("Unreviewed company boundary crosswalk version")
    if not isinstance(crosswalk, dict) or not all(
        isinstance(company, str) and isinstance(acronym, str)
        for company, acronym in crosswalk.items()
    ):
        raise Phase15SourceError("Invalid company boundary crosswalk")
    rows = payload.get("items")
    if not isinstance(rows, list) or not rows:
        raise Phase15SourceError("Empty company-performance publication")
    companies: dict[str, dict[str, Any]] = {}
    measures: list[dict[str, Any]] = []
    keys: set[tuple[str, str, str]] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise Phase15SourceError("Invalid company-performance row")
        company_id = text(raw.get("company_id"), "Ofwat company identity", 32)
        measure_code = text(raw.get("measure_code"), "performance measure code", 128)
        period = text(raw.get("reporting_period"), "reporting period", 32)
        key = company_id, measure_code, period
        if key in keys:
            raise Phase15SourceError("Duplicate company-performance fact")
        keys.add(key)
        companies.setdefault(
            company_id,
            {
                "company_id": company_id,
                "company_name": text(raw.get("company_name"), "company name", 256),
                "boundary_company_acronym": crosswalk.get(company_id),
            },
        )
        if "boundary_company_acronym" in raw:
            raise Phase15SourceError("Company boundary mapping must come from reviewed crosswalk")
        state = raw.get("value_state")
        value = raw.get("value")
        if state not in {"reported", "missing", "not_applicable"}:
            raise Phase15SourceError("Invalid performance value state")
        if state == "reported":
            value = number(value, "performance value")
        elif value is not None:
            raise Phase15SourceError("Missing performance value must not become zero")
        measures.append(
            {
                "company_id": company_id,
                "reporting_period": period,
                "measure_code": measure_code,
                "measure_name": text(raw.get("measure_name"), "measure name", 512),
                "value": value,
                "value_state": state,
                "unit": raw.get("unit"),
                "definition": raw.get("definition"),
                "publication": publication,
                "source_fields": raw,
            }
        )
    measures.sort(key=lambda row: (row["company_id"], row["measure_code"], row["reporting_period"]))
    return NormalizedProduct(
        "company-performance",
        sorted(companies.values(), key=lambda row: row["company_id"]),
        measures,
    )
