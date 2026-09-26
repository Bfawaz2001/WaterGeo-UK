"""Strict normalization for Thames Water's public discharge-status API."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SOURCE_URL = "https://api.thameswater.co.uk/opendata/v2/discharge/status"
DOCUMENTATION_URL = "https://docs.api.thameswater.co.uk/"
LICENCE_URL = "https://data.thameswater.co.uk/s/terms-of-service"
PUBLISHER = "Thames Water Utilities Limited"
API_VERSION = "2.0.1"
VERSION = "thames-water-discharge-status-v2.0.1-v1"
ATTRIBUTION = "Contains Thames Water discharge-status data licensed under its Open Data Terms."
NATIVE_SRID = 27700
MAX_RECORDS = 1000
ID_PATTERN = re.compile(r"^TWL[0-9]{5}$")
TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$")
STATUSES = frozenset({"Discharging", "Not discharging", "Offline"})
REQUIRED_FIELDS = {
    "locationName",
    "permitNumber",
    "locationGridRef",
    "x",
    "y",
    "receivingWaterCourse",
    "alertStatus",
    "statusChanged",
    "alertPast48Hours",
    "uniqueId",
}
OPTIONAL_FIELDS = {"mostRecentDischargeAlertStart", "mostRecentDischargeAlertStop"}


class ThamesDischargeError(ValueError):
    """The reviewed Thames Water source contract was not met."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ThamesDischargeError("Duplicate JSON member")
        result[key] = value
    return result


def decode(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_pairs)
        encoded(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ThamesDischargeError("Malformed Thames Water JSON") from error
    if not isinstance(value, dict):
        raise ThamesDischargeError("Expected Thames Water JSON object")
    return value


def _text(value: Any, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ThamesDischargeError(f"Invalid {field}")
    return value


def _timestamp(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _text(value, field, 32)
    if not TIMESTAMP_PATTERN.fullmatch(text):
        raise ThamesDischargeError(f"Invalid {field}")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ThamesDischargeError(f"Invalid {field}") from error
    if parsed.tzinfo is not None:
        raise ThamesDischargeError(f"Unexpected timezone in {field}")
    return text


@dataclass(frozen=True)
class NormalizedDischargeStatus:
    sites: list[dict[str, Any]]

    @property
    def sha256(self) -> str:
        return digest({"normalization_version": VERSION, "sites": self.sites})


def normalize(payload: dict[str, Any]) -> NormalizedDischargeStatus:
    meta = payload.get("meta")
    items = payload.get("items")
    if not isinstance(meta, dict) or set(meta) != {
        "publisher",
        "licence",
        "documentation",
        "version",
        "comment",
        "limit",
    }:
        raise ThamesDischargeError("Thames Water metadata schema changed")
    if meta != {
        "publisher": PUBLISHER,
        "licence": LICENCE_URL,
        "documentation": DOCUMENTATION_URL,
        "version": API_VERSION,
        "comment": "",
        "limit": "1000",
    }:
        raise ThamesDischargeError("Thames Water source contract changed")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_RECORDS:
        raise ThamesDischargeError("Invalid Thames Water item count")

    sites: list[dict[str, Any]] = []
    identities: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or not REQUIRED_FIELDS <= set(item) <= REQUIRED_FIELDS | OPTIONAL_FIELDS
        ):
            raise ThamesDischargeError("Thames Water item fields changed")
        identity = _text(item["uniqueId"], "site identity", 16)
        if not ID_PATTERN.fullmatch(identity) or identity in identities:
            raise ThamesDischargeError("Invalid or duplicate Thames Water site identity")
        identities.add(identity)
        x, y = item["x"], item["y"]
        if (
            type(x) not in (int, float)
            or type(y) not in (int, float)
            or not math.isfinite(x)
            or not math.isfinite(y)
            or not 0 <= x <= 700_000
            or not 0 <= y <= 1_300_000
        ):
            raise ThamesDischargeError("Invalid Thames Water coordinate")
        status = _text(item["alertStatus"], "alert status", 32)
        if status not in STATUSES or type(item["alertPast48Hours"]) is not bool:
            raise ThamesDischargeError("Invalid Thames Water alert state")
        start = _timestamp(
            item.get("mostRecentDischargeAlertStart"), "discharge start", optional=True
        )
        stop = _timestamp(item.get("mostRecentDischargeAlertStop"), "discharge stop", optional=True)
        if stop is not None and (start is None or stop < start):
            raise ThamesDischargeError("Invalid Thames Water discharge interval")
        sites.append(
            {
                "site_id": identity,
                "location_name": _text(item["locationName"], "location name"),
                "permit_number": _text(item["permitNumber"], "permit number", 64),
                "grid_reference": _text(item["locationGridRef"], "grid reference", 32),
                "easting": float(x),
                "northing": float(y),
                "receiving_watercourse": _text(
                    item["receivingWaterCourse"], "receiving watercourse"
                ),
                "alert_status": status,
                "status_changed": _timestamp(item["statusChanged"], "status changed"),
                "alert_past_48_hours": item["alertPast48Hours"],
                "most_recent_discharge_start": start,
                "most_recent_discharge_stop": stop,
                "source_fields": item,
            }
        )
    sites.sort(key=lambda row: row["site_id"])
    return NormalizedDischargeStatus(sites)
