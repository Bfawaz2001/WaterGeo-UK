"""Normalize the Environment Agency Catchment Data Explorer Cycle 3 hierarchy."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from shapely.geometry import shape

ROOT = "https://environment.data.gov.uk/catchment-planning"
PLAN_VERSION = "c3-plan"
VERSION = "ea-cde-c3-plan-v1"

IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

MAX_RIVER_BASIN_DISTRICTS = 32
MAX_MANAGEMENT_CATCHMENTS = 512
MAX_OPERATIONAL_CATCHMENTS = 4096
MAX_WATER_BODIES = 20000
MAX_GEOMETRY_FEATURES = 50000

ENTITY_KINDS = {
    "RiverBasinDistrict",
    "ManagementCatchment",
    "OperationalCatchment",
    "WaterBody",
}

ENTITY_LABELS = {
    "RiverBasinDistrict": "River Basin District",
    "ManagementCatchment": "Management Catchment",
    "OperationalCatchment": "Operational Catchment",
}

GEOMETRY_KINDS = {
    "Catchment": {"Polygon", "MultiPolygon"},
    "RiverLine": {"LineString", "MultiLineString"},
}

WATER_BODY_URI_ROOT = "http://environment.data.gov.uk/catchment-planning/so/WaterBody/"
GEOMETRY_TYPE_ROOT = "http://environment.data.gov.uk/catchment-planning/def/geometry/"


class CatchmentError(ValueError):
    """A Catchment Data Explorer source-contract check failed."""


def encoded(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatchmentError("Duplicate JSON member")
        result[key] = value
    return result


def decode_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CatchmentError("Malformed source JSON") from error

    if not isinstance(value, dict):
        raise CatchmentError("Expected source JSON object")

    try:
        encoded(value)
    except (ValueError, RecursionError) as error:
        raise CatchmentError("Invalid source JSON values") from error

    return value


def _string(value: Any, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CatchmentError(f"Invalid {field}")
    return value


def _identity(value: Any, field: str) -> str:
    normalized = _string(value, field, maximum=128)
    if not IDENTITY_PATTERN.fullmatch(normalized):
        raise CatchmentError(f"Invalid {field}")
    return normalized


def entity_url(kind: str, entity_id: str) -> str:
    if kind not in ENTITY_KINDS:
        raise CatchmentError("Unsupported catchment entity kind")

    entity_id = _identity(entity_id, "catchment identity")
    return f"{ROOT}/v/{PLAN_VERSION}/{kind}/{entity_id}"


def rbd_geojson_url(rbd_id: str) -> str:
    return entity_url("RiverBasinDistrict", rbd_id) + ".geojson"


class _HTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() == "title":
            self._in_title = True
            return

        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value is not None:
                self.links.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


@dataclass(frozen=True)
class ParsedPage:
    name: str
    links: dict[str, tuple[str, ...]]
    title: str


def _decode_html(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CatchmentError("Source HTML is not UTF-8") from error


def _hierarchy_links(
    hrefs: list[str],
    page_url: str,
) -> dict[str, tuple[str, ...]]:
    result: dict[str, set[str]] = {kind: set() for kind in ENTITY_KINDS}

    expected_prefix = f"/catchment-planning/v/{PLAN_VERSION}/"

    for href in hrefs:
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)

        if (
            parsed.scheme != "https"
            or parsed.hostname != "environment.data.gov.uk"
            or parsed.port not in (None, 443)
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            continue

        if not parsed.path.startswith(expected_prefix):
            continue

        tail = parsed.path[len(expected_prefix) :]
        pieces = tail.split("/")

        if len(pieces) != 2:
            continue

        kind, entity_id = pieces

        if kind not in ENTITY_KINDS:
            continue

        result[kind].add(_identity(entity_id, "linked catchment identity"))

    return {kind: tuple(sorted(ids)) for kind, ids in result.items()}


def hierarchy_links(body: bytes, page_url: str) -> dict[str, tuple[str, ...]]:
    parser = _HTMLParser()

    try:
        parser.feed(_decode_html(body))
        parser.close()
    except Exception as error:
        raise CatchmentError("Malformed source HTML") from error

    return _hierarchy_links(parser.links, page_url)


def parse_entity_page(
    body: bytes,
    *,
    kind: str,
    entity_id: str,
) -> ParsedPage:
    if kind not in ENTITY_LABELS:
        raise CatchmentError("Unsupported entity page kind")

    entity_id = _identity(entity_id, "catchment identity")
    page_url = entity_url(kind, entity_id)

    parser = _HTMLParser()

    try:
        parser.feed(_decode_html(body))
        parser.close()
    except Exception as error:
        raise CatchmentError("Malformed source HTML") from error

    title = " ".join("".join(parser.title_parts).split())

    suffix = " | Catchment Data Explorer"
    while title.endswith(suffix):
        title = title[: -len(suffix)].strip()

    label = ENTITY_LABELS[kind]

    if not title.endswith(label):
        raise CatchmentError("Unexpected catchment page title")

    name = title[: -len(label)].strip()

    if not name or len(name) > 512:
        raise CatchmentError("Invalid catchment entity name")

    return ParsedPage(
        name=name,
        links=_hierarchy_links(parser.links, page_url),
        title=title,
    )


def _geometry_record(
    feature: Any,
    *,
    feature_index: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise CatchmentError("Invalid GeoJSON feature")

    properties = feature.get("properties")
    geometry = feature.get("geometry")

    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise CatchmentError("Invalid GeoJSON feature members")

    water_body_id = _identity(
        properties.get("id"),
        "Water Body identity",
    )
    name = _string(
        properties.get("name"),
        "Water Body name",
        maximum=512,
    )

    publisher_uri = _string(
        properties.get("uri"),
        "Water Body publisher URI",
        maximum=2048,
    )

    if publisher_uri != WATER_BODY_URI_ROOT + water_body_id:
        raise CatchmentError("Unexpected Water Body publisher URI")

    water_body_type_value = properties.get("water-body-type")

    if not isinstance(water_body_type_value, dict):
        raise CatchmentError("Invalid Water Body type")

    if water_body_type_value.get("lang") != "en":
        raise CatchmentError("Unexpected Water Body type language")

    water_body_type = _string(
        water_body_type_value.get("string"),
        "Water Body type",
        maximum=128,
    )

    geometry_type_uri = _string(
        properties.get("geometry-type"),
        "publisher geometry type",
        maximum=2048,
    )

    if not geometry_type_uri.startswith(GEOMETRY_TYPE_ROOT):
        raise CatchmentError("Unexpected publisher geometry type URI")

    geometry_kind = geometry_type_uri[len(GEOMETRY_TYPE_ROOT) :]

    if geometry_kind not in GEOMETRY_KINDS:
        raise CatchmentError("Unreviewed publisher geometry kind")

    geometry_type = geometry.get("type")

    if geometry_type not in GEOMETRY_KINDS[geometry_kind]:
        raise CatchmentError("Geometry type contradicts publisher geometry kind")

    try:
        parsed_geometry = shape(geometry)
    except Exception as error:
        raise CatchmentError("Malformed Water Body geometry") from error

    if parsed_geometry.is_empty:
        raise CatchmentError("Empty Water Body geometry")

    bounds = parsed_geometry.bounds

    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise CatchmentError("Non-finite Water Body geometry bounds")

    min_x, min_y, max_x, max_y = bounds

    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise CatchmentError("Water Body geometry outside WGS84 range")

    water_body_source_fields = {
        key: value for key, value in properties.items() if key != "geometry-type"
    }

    metadata = {
        "water_body_id": water_body_id,
        "name": name,
        "water_body_type": water_body_type,
        "publisher_uri": publisher_uri,
        "source_fields": water_body_source_fields,
    }

    normalized_geometry = {
        "water_body_id": water_body_id,
        "feature_index": feature_index,
        "geometry_type_uri": geometry_type_uri,
        "geometry_kind": geometry_kind,
        "geometry": geometry,
        "source_fields": properties,
    }

    return water_body_id, metadata, normalized_geometry


def parse_rbd_geojson(
    body: bytes,
    *,
    rbd_id: str,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    _identity(rbd_id, "River Basin District identity")
    value = decode_json(body)

    if value.get("type") != "FeatureCollection":
        raise CatchmentError("Expected GeoJSON FeatureCollection")

    features = value.get("features")

    if not isinstance(features, list) or not features or len(features) > MAX_GEOMETRY_FEATURES:
        raise CatchmentError("Invalid GeoJSON feature collection")

    water_bodies: dict[str, dict[str, Any]] = {}
    geometries: list[dict[str, Any]] = []

    for feature_index, feature in enumerate(features):
        water_body_id, metadata, geometry = _geometry_record(
            feature,
            feature_index=feature_index,
        )

        existing = water_bodies.get(water_body_id)

        if existing is not None and existing != metadata:
            raise CatchmentError("Inconsistent Water Body metadata")

        water_bodies[water_body_id] = metadata
        geometries.append(geometry)

    return water_bodies, geometries


@dataclass(frozen=True)
class NormalizedCatchments:
    river_basin_districts: list[dict[str, Any]]
    management_catchments: list[dict[str, Any]]
    operational_catchments: list[dict[str, Any]]
    water_bodies: list[dict[str, Any]]
    geometries: list[dict[str, Any]]
    sha256: str

    @property
    def counts(self) -> dict[str, int]:
        return {
            "river_basin_district_count": len(self.river_basin_districts),
            "management_catchment_count": len(self.management_catchments),
            "operational_catchment_count": len(self.operational_catchments),
            "water_body_count": len(self.water_bodies),
            "geometry_feature_count": len(self.geometries),
        }


def normalize(
    *,
    root_html: bytes,
    rbd_html: dict[str, bytes],
    management_html: dict[str, bytes],
    operational_html: dict[str, bytes],
    rbd_geojson: dict[str, bytes],
) -> NormalizedCatchments:
    root_links = hierarchy_links(
        root_html,
        f"{ROOT}/v/{PLAN_VERSION}",
    )

    rbd_ids = set(root_links["RiverBasinDistrict"])

    if (
        not rbd_ids
        or len(rbd_ids) > MAX_RIVER_BASIN_DISTRICTS
        or set(rbd_html) != rbd_ids
        or set(rbd_geojson) != rbd_ids
    ):
        raise CatchmentError("Incomplete River Basin District evidence")

    river_basin_districts: dict[str, dict[str, Any]] = {}
    expected_management: dict[str, str] = {}

    for rbd_id in sorted(rbd_ids):
        page = parse_entity_page(
            rbd_html[rbd_id],
            kind="RiverBasinDistrict",
            entity_id=rbd_id,
        )

        children = page.links["ManagementCatchment"]

        if not children:
            raise CatchmentError("River Basin District has no Management Catchments")

        river_basin_districts[rbd_id] = {
            "river_basin_district_id": rbd_id,
            "name": page.name,
            "publisher_uri": entity_url(
                "RiverBasinDistrict",
                rbd_id,
            ),
            "source_fields": {
                "title": page.title,
                "management_catchments": list(children),
            },
        }

        for management_id in children:
            if management_id in expected_management:
                raise CatchmentError(
                    "Management Catchment has multiple River Basin District parents"
                )
            expected_management[management_id] = rbd_id

    if (
        not expected_management
        or len(expected_management) > MAX_MANAGEMENT_CATCHMENTS
        or set(management_html) != set(expected_management)
    ):
        raise CatchmentError("Incomplete Management Catchment evidence")

    management_catchments: dict[str, dict[str, Any]] = {}
    expected_operational: dict[str, tuple[str, str]] = {}

    for management_id in sorted(expected_management):
        expected_rbd_id = expected_management[management_id]

        page = parse_entity_page(
            management_html[management_id],
            kind="ManagementCatchment",
            entity_id=management_id,
        )

        parents = page.links["RiverBasinDistrict"]

        if parents != (expected_rbd_id,):
            raise CatchmentError("Management Catchment parent relationship mismatch")

        children = page.links["OperationalCatchment"]

        if not children:
            raise CatchmentError("Management Catchment has no Operational Catchments")

        management_catchments[management_id] = {
            "management_catchment_id": management_id,
            "river_basin_district_id": expected_rbd_id,
            "name": page.name,
            "publisher_uri": entity_url(
                "ManagementCatchment",
                management_id,
            ),
            "source_fields": {
                "title": page.title,
                "river_basin_district_id": expected_rbd_id,
                "operational_catchments": list(children),
            },
        }

        for operational_id in children:
            if operational_id in expected_operational:
                raise CatchmentError(
                    "Operational Catchment has multiple Management Catchment parents"
                )

            expected_operational[operational_id] = (
                management_id,
                expected_rbd_id,
            )

    if (
        not expected_operational
        or len(expected_operational) > MAX_OPERATIONAL_CATCHMENTS
        or set(operational_html) != set(expected_operational)
    ):
        raise CatchmentError("Incomplete Operational Catchment evidence")

    operational_catchments: dict[str, dict[str, Any]] = {}
    expected_water_bodies: dict[str, tuple[str, str, str]] = {}

    for operational_id in sorted(expected_operational):
        expected_management_id, expected_rbd_id = expected_operational[operational_id]

        page = parse_entity_page(
            operational_html[operational_id],
            kind="OperationalCatchment",
            entity_id=operational_id,
        )

        if page.links["RiverBasinDistrict"] != (expected_rbd_id,):
            raise CatchmentError("Operational Catchment River Basin District mismatch")

        if page.links["ManagementCatchment"] != (expected_management_id,):
            raise CatchmentError("Operational Catchment Management Catchment mismatch")

        children = page.links["WaterBody"]

        operational_catchments[operational_id] = {
            "operational_catchment_id": operational_id,
            "management_catchment_id": expected_management_id,
            "river_basin_district_id": expected_rbd_id,
            "name": page.name,
            "publisher_uri": entity_url(
                "OperationalCatchment",
                operational_id,
            ),
            "source_fields": {
                "title": page.title,
                "river_basin_district_id": expected_rbd_id,
                "management_catchment_id": expected_management_id,
                "water_bodies": list(children),
            },
        }

        for water_body_id in children:
            if water_body_id in expected_water_bodies:
                raise CatchmentError("Water Body has multiple Operational Catchment parents")

            expected_water_bodies[water_body_id] = (
                operational_id,
                expected_management_id,
                expected_rbd_id,
            )

    if not expected_water_bodies or len(expected_water_bodies) > MAX_WATER_BODIES:
        raise CatchmentError("Invalid Water Body hierarchy")

    geometry_water_bodies: dict[str, dict[str, Any]] = {}
    geometries: list[dict[str, Any]] = []

    for rbd_id in sorted(rbd_ids):
        metadata, rbd_geometries = parse_rbd_geojson(
            rbd_geojson[rbd_id],
            rbd_id=rbd_id,
        )

        for water_body_id, row in metadata.items():
            expected_parent = expected_water_bodies.get(water_body_id)

            if expected_parent is None:
                raise CatchmentError("GeoJSON contains Water Body absent from hierarchy")

            if expected_parent[2] != rbd_id:
                raise CatchmentError("Water Body geometry appears in wrong River Basin District")

            existing = geometry_water_bodies.get(water_body_id)

            if existing is not None and existing != row:
                raise CatchmentError("Water Body metadata differs across source geometry")

            geometry_water_bodies[water_body_id] = row

        geometries.extend(rbd_geometries)

    if set(geometry_water_bodies) != set(expected_water_bodies):
        raise CatchmentError("Hierarchy and GeoJSON Water Body inventories differ")

    if len(geometries) > MAX_GEOMETRY_FEATURES:
        raise CatchmentError("Geometry feature budget exceeded")

    water_bodies: dict[str, dict[str, Any]] = {}

    for water_body_id in sorted(expected_water_bodies):
        (
            operational_id,
            management_id,
            rbd_id,
        ) = expected_water_bodies[water_body_id]

        source = geometry_water_bodies[water_body_id]

        water_bodies[water_body_id] = {
            "water_body_id": water_body_id,
            "operational_catchment_id": operational_id,
            "management_catchment_id": management_id,
            "river_basin_district_id": rbd_id,
            "name": source["name"],
            "water_body_type": source["water_body_type"],
            "publisher_uri": source["publisher_uri"],
            "source_fields": source["source_fields"],
        }

    rows = [
        [river_basin_districts[key] for key in sorted(river_basin_districts)],
        [management_catchments[key] for key in sorted(management_catchments)],
        [operational_catchments[key] for key in sorted(operational_catchments)],
        [water_bodies[key] for key in sorted(water_bodies)],
        sorted(
            geometries,
            key=lambda row: (
                row["water_body_id"],
                row["feature_index"],
            ),
        ),
    ]

    normalized_sha256 = digest(
        {
            "version": VERSION,
            "plan_version": PLAN_VERSION,
            "rows": rows,
        }
    )

    return NormalizedCatchments(
        river_basin_districts=rows[0],
        management_catchments=rows[1],
        operational_catchments=rows[2],
        water_bodies=rows[3],
        geometries=rows[4],
        sha256=normalized_sha256,
    )
