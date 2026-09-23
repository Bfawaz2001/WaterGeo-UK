"""Strict normalization for the reviewed Stream reservoir-level edition."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

ITEM_ID = "0bbd0dd0487346a893d4d615aad9d289"
ITEM_TITLE = "Severn Trent Water Raw Water Storage - Reservoir Levels 2025"
PUBLISHER = "Severn Trent Water"
EDITION = "2025"
VERSION = "stream-severn-trent-reservoir-levels-2025-v1"
LICENCE = "Creative Commons Attribution 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = (
    "Severn Trent Water Raw Water Storage - Reservoir Levels 2025 "
    "© Severn Trent Water, licensed under CC BY 4.0."
)
ITEM_URL = f"https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}"
PUBLIC_ITEM_URL = f"https://www.streamwaterdata.co.uk/datasets/{ITEM_ID}"
SERVICE_ROOT = (
    "https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/"
    "Severn_Trent_Water_Raw_Water_Storage_-_Reservoir_Levels_2025/FeatureServer"
)
LAYER_URL = SERVICE_ROOT + "/0"
LAYER_NAME = "Sheet1"
NATIVE_SRID = 3857
PRESENTATION_SRID = 4326

MAX_RECORDS = 2000
MAX_RESERVOIRS = 256
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
FIELDS = (
    "RESERVOIR_ID",
    "RESERVOIR_NAME",
    "DATE",
    "LATITUDE",
    "LONGITUDE",
    "CAPACITY",
    "CAPACITY_UNITS",
    "CURRENT_LEVEL",
    "CURRENT_LEVEL_UNITS",
    "CURRENT_PERCENTAGE",
    "FID",
)


class StreamReservoirError(ValueError):
    """The reviewed Stream source contract was not met."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StreamReservoirError("Duplicate JSON member")
        result[key] = value
    return result


def decode(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_pairs)
        encoded(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise StreamReservoirError("Malformed Stream JSON") from error
    if not isinstance(value, dict):
        raise StreamReservoirError("Expected Stream JSON object")
    return value


def _string(value: Any, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise StreamReservoirError(f"Invalid {field}")
    return value


def _finite(value: Any, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise StreamReservoirError(f"Invalid {field}")
    return float(value)


def _source_number(value: Any, field: str) -> float:
    text = _string(value, field, 64)
    try:
        parsed = float(text)
    except ValueError as error:
        raise StreamReservoirError(f"Invalid {field}") from error
    if not math.isfinite(parsed):
        raise StreamReservoirError(f"Invalid {field}")
    return parsed


def parse_item(body: bytes) -> dict[str, Any]:
    item = decode(body)
    if (
        item.get("id") != ITEM_ID
        or item.get("title") != ITEM_TITLE
        or item.get("type") != "Feature Service"
        or item.get("access") != "public"
        or item.get("accessInformation") != PUBLISHER
        or item.get("url") != SERVICE_ROOT
        or type(item.get("created")) is not int
        or type(item.get("modified")) is not int
        or item["created"] <= 0
        or item["modified"] < item["created"]
        or "CC BY 4.0" not in _string(item.get("licenseInfo"), "item licence", 8192)
    ):
        raise StreamReservoirError("Stream item contract changed")
    return item


def parse_layer(body: bytes) -> dict[str, Any]:
    layer = decode(body)
    extent = layer.get("extent")
    reference = extent.get("spatialReference") if isinstance(extent, dict) else None
    expected_types = {
        "RESERVOIR_ID": "esriFieldTypeString",
        "RESERVOIR_NAME": "esriFieldTypeString",
        "DATE": "esriFieldTypeDate",
        "LATITUDE": "esriFieldTypeString",
        "LONGITUDE": "esriFieldTypeString",
        "CAPACITY": "esriFieldTypeString",
        "CAPACITY_UNITS": "esriFieldTypeString",
        "CURRENT_LEVEL": "esriFieldTypeString",
        "CURRENT_LEVEL_UNITS": "esriFieldTypeString",
        "CURRENT_PERCENTAGE": "esriFieldTypeDouble",
        "FID": "esriFieldTypeOID",
    }
    fields = layer.get("fields")
    time_reference = layer.get("dateFieldsTimeReference")
    actual = (
        {field.get("name"): field.get("type") for field in fields}
        if isinstance(fields, list) and all(isinstance(field, dict) for field in fields)
        else {}
    )
    if (
        layer.get("id") != 0
        or layer.get("name") != LAYER_NAME
        or layer.get("type") != "Feature Layer"
        or layer.get("geometryType") != "esriGeometryPoint"
        or layer.get("objectIdField") != "FID"
        or layer.get("capabilities") != "Query"
        or type(layer.get("maxRecordCount")) is not int
        or layer["maxRecordCount"] < 250
        or not isinstance(reference, dict)
        or reference.get("latestWkid") != NATIVE_SRID
        or actual != expected_types
        or time_reference
        != {"timeZone": "UTC", "timeZoneIANA": "Etc/UTC", "respectsDaylightSaving": False}
    ):
        raise StreamReservoirError("Stream layer schema changed")
    return layer


def parse_ids(body: bytes) -> list[int]:
    payload = decode(body)
    values = payload.get("objectIds")
    if (
        payload.get("objectIdFieldName") != "FID"
        or not isinstance(values, list)
        or not 1 <= len(values) <= MAX_RECORDS
        or any(type(value) is not int or value <= 0 for value in values)
        or len(values) != len(set(values))
    ):
        raise StreamReservoirError("Invalid Stream object-ID set")
    return sorted(values)


@dataclass(frozen=True)
class NormalizedReservoirs:
    reservoirs: list[dict[str, Any]]
    readings: list[dict[str, Any]]

    @property
    def sha256(self) -> str:
        return digest(
            {
                "normalization_version": VERSION,
                "edition": EDITION,
                "reservoirs": self.reservoirs,
                "readings": self.readings,
            }
        )


def normalize(collections: list[dict[str, Any]], expected_ids: list[int]) -> NormalizedReservoirs:
    records: list[dict[str, Any]] = []
    for collection in collections:
        if collection.get("type") != "FeatureCollection" or collection.get("crs") != {
            "type": "name",
            "properties": {"name": "EPSG:4326"},
        }:
            raise StreamReservoirError("Expected Stream GeoJSON FeatureCollection")
        features = collection.get("features")
        if not isinstance(features, list):
            raise StreamReservoirError("Invalid Stream GeoJSON features")
        records.extend(features)
    if len(records) != len(expected_ids) or len(records) > MAX_RECORDS:
        raise StreamReservoirError("Incomplete Stream reservoir retrieval")

    reservoirs: dict[str, dict[str, Any]] = {}
    readings: dict[tuple[str, str], dict[str, Any]] = {}
    object_ids: set[int] = set()
    for feature in records:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise StreamReservoirError("Invalid Stream GeoJSON feature")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or set(properties) != set(FIELDS):
            raise StreamReservoirError("Stream reservoir fields changed")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") != "Point"
            or not isinstance(geometry.get("coordinates"), list)
            or len(geometry["coordinates"]) != 2
        ):
            raise StreamReservoirError("Invalid Stream reservoir point")

        reservoir_id = _string(properties["RESERVOIR_ID"], "reservoir identity", 64)
        if not ID_PATTERN.fullmatch(reservoir_id):
            raise StreamReservoirError("Invalid reservoir identity")
        name = _string(properties["RESERVOIR_NAME"], "reservoir name", 256)
        object_id = properties["FID"]
        timestamp = properties["DATE"]
        if type(object_id) is not int or object_id <= 0 or type(timestamp) is not int:
            raise StreamReservoirError("Invalid Stream reading identity")
        if object_id in object_ids:
            raise StreamReservoirError("Duplicate Stream object identity")
        object_ids.add(object_id)
        moment = datetime.fromtimestamp(timestamp / 1000, UTC)
        if moment.year != int(EDITION) or int(moment.timestamp() * 1000) != timestamp:
            raise StreamReservoirError("Invalid Stream reading date")
        observed_at = moment.isoformat()

        latitude = _source_number(properties["LATITUDE"], "latitude")
        longitude = _source_number(properties["LONGITUDE"], "longitude")
        point = geometry["coordinates"]
        point_lon = _finite(point[0], "point longitude")
        point_lat = _finite(point[1], "point latitude")
        if (
            not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
            or abs(point_lon - longitude) > 1e-9
            or abs(point_lat - latitude) > 1e-9
        ):
            raise StreamReservoirError("Stream point and coordinate fields disagree")

        capacity = _source_number(properties["CAPACITY"], "capacity")
        current_level = _source_number(properties["CURRENT_LEVEL"], "current level")
        percentage = _finite(properties["CURRENT_PERCENTAGE"], "current percentage")
        capacity_unit = _string(properties["CAPACITY_UNITS"], "capacity unit", 32)
        level_unit = _string(properties["CURRENT_LEVEL_UNITS"], "level unit", 32)
        if (
            capacity <= 0
            or current_level < 0
            or not 0 <= percentage <= 100
            or capacity_unit != "ML"
            or level_unit != "ML"
        ):
            raise StreamReservoirError("Unsupported Stream reservoir quantity")

        reservoir = {
            "reservoir_id": reservoir_id,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "capacity": capacity,
            "capacity_unit": capacity_unit,
        }
        previous = reservoirs.setdefault(reservoir_id, reservoir)
        if previous != reservoir:
            raise StreamReservoirError("Reservoir metadata changed within the edition")
        key = (reservoir_id, observed_at)
        if key in readings:
            raise StreamReservoirError("Duplicate reservoir/timestamp reading")
        readings[key] = {
            "reservoir_id": reservoir_id,
            "observed_at": observed_at,
            "current_level": current_level,
            "current_level_unit": level_unit,
            "current_percentage": percentage,
            "publisher_object_id": object_id,
            "source_fields": properties,
        }
    if sorted(object_ids) != expected_ids or not 1 <= len(reservoirs) <= MAX_RESERVOIRS:
        raise StreamReservoirError("Stream object identities changed during paging")
    return NormalizedReservoirs(
        [reservoirs[key] for key in sorted(reservoirs)],
        [readings[key] for key in sorted(readings)],
    )
