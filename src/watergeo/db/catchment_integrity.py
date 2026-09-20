"""Recompute catchment retry integrity from actual stored child rows."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from shapely import set_srid, to_wkb
from shapely.geometry import shape
from sqlalchemy import Connection, text

from watergeo.ingestion.catchments import (
    CatchmentError,
    NormalizedCatchments,
    digest,
)


def _canonical(value: Any) -> Any:
    """Preserve typed database identity during exact-content comparison."""
    if value is None or isinstance(value, (str, bool)):
        return [type(value).__name__, value]

    if isinstance(value, Decimal):
        sign, digits, exponent = value.as_tuple()

        if not value.is_finite():
            raise CatchmentError("Existing catchment snapshot stored content mismatch")

        digits_text = "".join(str(digit) for digit in digits)

        if not any(digits):
            return ["decimal", 0, "0", 0]

        trailing = len(digits_text) - len(digits_text.rstrip("0"))

        return [
            "decimal",
            sign,
            digits_text.rstrip("0"),
            int(exponent) + trailing,
        ]

    if isinstance(value, float):
        return ["float8", value.hex()]

    if isinstance(value, int):
        return ["integer", str(value)]

    if isinstance(value, list):
        return ["array", [_canonical(item) for item in value]]

    if isinstance(value, dict):
        return [
            "object",
            [[key, _canonical(value[key])] for key in sorted(value)],
        ]

    raise CatchmentError("Unsupported stored catchment snapshot value")


def _source_json(raw: str) -> Any:
    return json.loads(
        raw,
        parse_float=Decimal,
        parse_int=Decimal,
    )


def _expected_geometry_wkb(row: dict[str, Any]) -> str:
    try:
        geometry = set_srid(shape(row["geometry"]), 4326)
        raw_wkb = to_wkb(
            geometry,
            byte_order=1,
            include_srid=True,
        )
        if not isinstance(raw_wkb, bytes):
            raise CatchmentError("Unexpected normalized catchment geometry encoding")
        return raw_wkb.hex()
    except CatchmentError:
        raise
    except Exception as error:
        raise CatchmentError(
            "Invalid normalized catchment geometry during retry verification"
        ) from error


def verify_stored_content(
    connection: Connection,
    snapshot_id: UUID,
    data: NormalizedCatchments,
) -> None:
    expected_geometries = [
        {
            "water_body_id": row["water_body_id"],
            "feature_index": row["feature_index"],
            "geometry_type_uri": row["geometry_type_uri"],
            "geometry_kind": row["geometry_kind"],
            "geometry_wkb": _expected_geometry_wkb(row),
            "source_fields": row["source_fields"],
        }
        for row in data.geometries
    ]

    expected = [
        data.river_basin_districts,
        data.management_catchments,
        data.operational_catchments,
        data.water_bodies,
        expected_geometries,
    ]

    statements = (
        """
        SELECT
            river_basin_district_id,
            name,
            publisher_uri,
            source_fields::text AS source_fields
        FROM watergeo.catchment_river_basin_district
        WHERE snapshot_id = :id
        ORDER BY river_basin_district_id COLLATE "C"
        """,
        """
        SELECT
            management_catchment_id,
            river_basin_district_id,
            name,
            publisher_uri,
            source_fields::text AS source_fields
        FROM watergeo.catchment_management
        WHERE snapshot_id = :id
        ORDER BY management_catchment_id COLLATE "C"
        """,
        """
        SELECT
            operational_catchment_id,
            management_catchment_id,
            river_basin_district_id,
            name,
            publisher_uri,
            source_fields::text AS source_fields
        FROM watergeo.catchment_operational
        WHERE snapshot_id = :id
        ORDER BY operational_catchment_id COLLATE "C"
        """,
        """
        SELECT
            water_body_id,
            operational_catchment_id,
            management_catchment_id,
            river_basin_district_id,
            name,
            water_body_type,
            publisher_uri,
            source_fields::text AS source_fields
        FROM watergeo.catchment_water_body
        WHERE snapshot_id = :id
        ORDER BY water_body_id COLLATE "C"
        """,
        """
        SELECT
            water_body_id,
            feature_index,
            geometry_type_uri,
            geometry_kind,
            encode(
                public.ST_AsEWKB(geom, 'NDR'),
                'hex'
            ) AS geometry_wkb,
            source_fields::text AS source_fields
        FROM watergeo.catchment_water_body_geometry
        WHERE snapshot_id = :id
        ORDER BY
            water_body_id COLLATE "C",
            feature_index
        """,
    )

    actual: list[list[dict[str, Any]]] = []

    for statement, expected_rows in zip(
        statements,
        expected,
        strict=True,
    ):
        rows = [
            dict(row)
            for row in connection.execute(
                text(statement),
                {"id": snapshot_id},
            ).mappings()
        ]

        if len(rows) != len(expected_rows):
            raise CatchmentError("Existing catchment snapshot stored content mismatch")

        actual.append(
            [
                {
                    **row,
                    "source_fields": _source_json(row["source_fields"]),
                }
                for row in rows
            ]
        )

    expected_json = [
        [
            {
                **row,
                "source_fields": _source_json(
                    json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    )
                ),
            }
            for row in rows
        ]
        for rows in expected
    ]

    if digest(_canonical(actual)) != digest(_canonical(expected_json)):
        raise CatchmentError("Existing catchment snapshot stored content mismatch")
