"""Recompute Water Quality retry integrity from actual stored child rows."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from shapely import Point, set_srid, to_wkb
from sqlalchemy import Connection, text

from watergeo.ingestion.water_quality import (
    Normalized,
    WaterQualityError,
    digest,
)


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return [type(value).__name__, value]

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise WaterQualityError("Existing snapshot stored content mismatch")

        sign, digits, exponent = value.as_tuple()
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

    raise WaterQualityError("Unsupported stored snapshot value")


def _source_json(raw: str) -> Any:
    return json.loads(
        raw,
        parse_float=Decimal,
        parse_int=Decimal,
    )


def verify_stored_content(
    connection: Connection,
    snapshot_id: UUID,
    data: Normalized,
) -> None:
    expected_rows = []

    for row in data.sampling_points:
        geometry = None

        if row["latitude"] is not None:
            geometry = to_wkb(
                set_srid(
                    Point(
                        row["longitude"],
                        row["latitude"],
                    ),
                    4326,
                ),
                byte_order=1,
                include_srid=True,
            ).hex()

        expected_rows.append(
            {
                **row,
                "geometry_wkb": geometry,
            }
        )

    rows = [
        dict(row)
        for row in connection.execute(
            text("""
                SELECT
                    sampling_point_id,
                    source_uri,
                    alt_label,
                    pref_label,
                    latitude,
                    longitude,
                    encode(
                        public.ST_AsEWKB(geom, 'NDR'),
                        'hex'
                    ) AS geometry_wkb,
                    status::text AS status,
                    sampling_point_type::text AS sampling_point_type,
                    region::text AS region,
                    area::text AS area,
                    sub_area::text AS sub_area,
                    source_fields::text AS source_fields
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id = :id
                ORDER BY sampling_point_id COLLATE "C"
            """),
            {"id": snapshot_id},
        ).mappings()
    ]

    if len(rows) != len(expected_rows):
        raise WaterQualityError("Existing snapshot stored content mismatch")

    json_fields = (
        "status",
        "sampling_point_type",
        "region",
        "area",
        "sub_area",
        "source_fields",
    )

    actual = []
    for row in rows:
        converted = dict(row)

        for field in json_fields:
            if converted[field] is not None:
                converted[field] = _source_json(converted[field])

        actual.append(converted)

    expected = []
    for row in expected_rows:
        converted = dict(row)

        for field in json_fields:
            value = converted[field]

            if value is not None:
                converted[field] = _source_json(
                    json.dumps(
                        value,
                        allow_nan=False,
                    )
                )

        expected.append(converted)

    if digest(_canonical(actual)) != digest(_canonical(expected)):
        raise WaterQualityError("Existing snapshot stored content mismatch")
