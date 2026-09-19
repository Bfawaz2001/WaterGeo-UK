"""Strict normalization of the reviewed EA river-level/flow source contract."""

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

ROOT = "https://environment.data.gov.uk/hydrology"
IDENTITY_ROOT = "http://environment.data.gov.uk/hydrology/id/"
LICENCE = "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
VERSION = "ea-hydrology-river-v1"
ATTRIBUTION = "© Environment Agency copyright and/or database right 2015. All rights reserved."
ID_PATTERN = r"^[A-Za-z0-9_.-]{1,256}$"
MAX_MEASURES = 64


class HydrologyError(ValueError):
    """A source contract, completeness or evidence check failed."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HydrologyError("Duplicate JSON member")
        result[key] = value
    return result


def decode(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise HydrologyError("Malformed JSON response") from error
    if not isinstance(value, dict):
        raise HydrologyError("Expected JSON object")
    # Also reject non-finite constants in optional/raw fields.
    try:
        encoded(value)
    except (ValueError, RecursionError) as error:
        raise HydrologyError("Invalid JSON values") from error
    return value


def string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise HydrologyError(f"Invalid {field}")
    return value


def number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HydrologyError(f"Invalid numeric {field}")
    try:
        result = float(value)
    except OverflowError as error:
        raise HydrologyError(f"Invalid numeric {field}") from error
    if not math.isfinite(result):
        raise HydrologyError(f"Non-finite {field}")
    return result


def identity(value: Any, kind: str) -> str:
    uri = string(value, "source URI")
    prefix = IDENTITY_ROOT + kind + "/"
    if not uri.startswith(prefix) or not re.fullmatch(ID_PATTERN, uri[len(prefix) :]):
        raise HydrologyError("Unexpected publisher identity")
    return uri[len(prefix) :]


def reference(value: Any, kind: str) -> str:
    if not isinstance(value, dict):
        raise HydrologyError("Invalid source reference")
    return identity(value.get("@id"), kind)


def timestamp(value: Any) -> datetime:
    raw = string(value, "observation timestamp")
    if not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?"
        r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?",
        raw,
    ):
        raise HydrologyError("Invalid observation timestamp")
    try:
        parsed = datetime.fromisoformat(raw)
        # Explicit EA GMT contract, not the machine's local timezone.
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, OverflowError) as error:
        raise HydrologyError("Invalid observation timestamp") from error


def location(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    lat, lon = raw.get("lat"), raw.get("long")
    east, north = raw.get("easting"), raw.get("northing")
    if (east is None) != (north is None):
        raise HydrologyError("Partial British National Grid location")
    if east is not None:
        number(east, "easting")
        number(north, "northing")
    if lat is None and lon is None:
        if east is not None:
            raise HydrologyError("BNG-only location requires a new source assessment")
        return None, None
    if lat is None or lon is None:
        raise HydrologyError("Partial WGS84 location")
    latitude, longitude = number(lat, "latitude"), number(lon, "longitude")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HydrologyError("Coordinates outside WGS84 range")
    # WGS84 is authoritative. BNG is retained, not transformed or used to replace it.
    return latitude, longitude


@dataclass(frozen=True)
class Normalized:
    stations: list[dict[str, Any]]
    measures: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    sha256: str

    @property
    def counts(self) -> dict[str, int]:
        located = sum(row["latitude"] is not None for row in self.stations)
        return {
            "station_count": len(self.stations),
            "station_with_location_count": located,
            "station_without_location_count": len(self.stations) - located,
            "measure_count": len(self.measures),
            "latest_observation_count": len(self.observations),
        }


def normalize(records: dict[str, list[dict[str, Any]]]) -> Normalized:
    stations: dict[str, dict[str, Any]] = {}
    measures: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}
    for raw in records["stations"]:
        sid = identity(raw.get("@id"), "stations")
        if raw.get("notation") != sid or sid in stations:
            raise HydrologyError("Duplicate or inconsistent station identity")
        labels = raw.get("label")
        if isinstance(labels, str):
            labels = [labels]
        if not isinstance(labels, list) or not labels:
            raise HydrologyError("Invalid station labels")
        labels = [string(label, "station label") for label in labels]
        lat, lon = location(raw)
        stations[sid] = {
            "station_id": sid,
            "source_uri": raw["@id"],
            "labels": labels,
            "latitude": lat,
            "longitude": lon,
            "source_fields": raw,
        }
    if not stations:
        raise HydrologyError("Empty station snapshot")
    for raw in records["measures"]:
        mid = identity(raw.get("@id"), "measures")
        sid = reference(raw.get("station"), "stations")
        if raw.get("notation") != mid or mid in measures or sid not in stations:
            raise HydrologyError("Duplicate measure or invalid measure relationship")
        parameter = string(raw.get("parameter"), "parameter")
        unit = string(raw.get("unitName"), "unitName")
        if (parameter, unit) not in {("level", "m"), ("flow", "m3/s")}:
            raise HydrologyError("Measure outside reviewed river scope/units")
        period = raw.get("period")
        if type(period) is not int or not 1 <= period <= 86400:
            raise HydrologyError("Invalid measurement period")
        for field in ("valueStatistic", "observedProperty", "observationType", "unit"):
            if not isinstance(raw.get(field), dict):
                raise HydrologyError(f"Invalid {field}")
            string(raw[field].get("@id"), field)
        expected = "waterLevel" if parameter == "level" else "waterFlow"
        if (
            raw["observedProperty"]["@id"]
            != "http://environment.data.gov.uk/reference/def/op/" + expected
        ):
            raise HydrologyError("Inconsistent observed property")
        measures[mid] = {
            "measure_id": mid,
            "station_id": sid,
            "source_uri": raw["@id"],
            "parameter": parameter,
            "unit_name": unit,
            "period": period,
            "source_fields": raw,
        }
    if (
        not measures
        or max(Counter(x["station_id"] for x in measures.values()).values()) > MAX_MEASURES
    ):
        raise HydrologyError("Empty or excessive station measure definitions")
    # Embedded station references independently check scoped measure completeness.
    station_measures: dict[str, set[str]] = {sid: set() for sid in stations}
    for mid, measure in measures.items():
        station_measures[measure["station_id"]].add(mid)
    for sid, station in stations.items():
        embedded = station["source_fields"].get("measures")
        if isinstance(embedded, dict):
            embedded = [embedded]
        if not isinstance(embedded, list):
            raise HydrologyError("Missing station measure references")
        expected_ids: set[str] = set()
        for item in embedded:
            if not isinstance(item, dict):
                raise HydrologyError("Malformed station measure reference")
            if item.get("parameter") in ("level", "flow"):
                mid = identity(item.get("@id"), "measures")
                if mid in expected_ids:
                    raise HydrologyError("Duplicate embedded measure reference")
                expected_ids.add(mid)
        actual = station_measures[sid]
        if actual != expected_ids:
            raise HydrologyError("Incomplete or inconsistent station measure references")
    for raw in records["observations"]:
        mid = reference(raw.get("measure"), "measures")
        if mid not in measures or mid in observations:
            raise HydrologyError("Unknown or duplicate latest measure")
        observed_at = timestamp(raw.get("dateTime"))
        value = raw.get("value")
        if value is None:
            if raw.get("quality") != "Missing":
                raise HydrologyError("Missing observation value without Missing quality")
        else:
            value = number(value, "observation value")
            if raw.get("quality") == "Missing":
                raise HydrologyError("Numeric observation contradicts Missing quality")
        observations[mid] = {
            "measure_id": mid,
            "observed_at": observed_at.isoformat(),
            "value": value,
            "source_fields": raw,
        }
    rows = [
        [mapping[key] for key in sorted(mapping)] for mapping in (stations, measures, observations)
    ]
    return Normalized(rows[0], rows[1], rows[2], digest({"version": VERSION, "rows": rows}))
