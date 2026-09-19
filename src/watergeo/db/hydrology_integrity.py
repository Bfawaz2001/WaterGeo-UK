"""Recompute retry integrity from actual child rows, independently of stored hashes."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from shapely import Point, set_srid, to_wkb
from sqlalchemy import Connection, text

from watergeo.ingestion.hydrology import HydrologyError, Normalized, digest


def _canonical(value: Any) -> Any:
    """Typed values prevent JSON booleans/numbers from comparing equal in Python."""
    if value is None or isinstance(value, (str, bool)):
        return [type(value).__name__, value]
    if isinstance(value, Decimal):
        # JSONB numbers are decimal values, independent of scale or exponent spelling.
        # Work with digits directly: Decimal.normalize() can round to context precision.
        sign, digits, exponent = value.as_tuple()
        if not value.is_finite():
            raise HydrologyError("Existing snapshot stored content mismatch")
        digits_text = "".join(str(digit) for digit in digits)
        if not any(digits):
            return ["decimal", 0, "0", 0]
        trailing = len(digits_text) - len(digits_text.rstrip("0"))
        return ["decimal", sign, digits_text.rstrip("0"), int(exponent) + trailing]
    if isinstance(value, float):
        # Queryable float8 values use exact binary identity, including signed zero.
        return ["float8", value.hex()]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise HydrologyError("Existing snapshot stored content mismatch")
        return ["timestamp", value.astimezone(UTC).isoformat(timespec="microseconds")]
    if isinstance(value, list):
        return ["array", [_canonical(item) for item in value]]
    if isinstance(value, dict):
        return ["object", [[key, _canonical(value[key])] for key in sorted(value)]]
    raise HydrologyError("Unsupported stored snapshot value")


def _source_json(raw: str) -> Any:
    # Avoid rounding a privileged JSONB numeric alteration through Python float parsing.
    return json.loads(raw, parse_float=Decimal, parse_int=Decimal)


def verify_stored_content(connection: Connection, snapshot_id: UUID, data: Normalized) -> None:
    expected_stations = []
    for row in data.stations:
        geometry = None
        if row["latitude"] is not None:
            geometry = to_wkb(
                set_srid(Point(row["longitude"], row["latitude"]), 4326),
                byte_order=1,
                include_srid=True,
            ).hex()
        expected_stations.append({**row, "geometry_wkb": geometry})
    expected = [
        expected_stations,
        data.measures,
        [
            {**row, "observed_at": datetime.fromisoformat(row["observed_at"])}
            for row in data.observations
        ],
    ]
    # Explicit columns cover the full normalized contract. JSONB is fetched as text
    # and parsed with exact decimal numbers; geometry is fixed-endian EWKB (with SRID).
    statements = (
        """SELECT station_id, source_uri, labels, latitude, longitude,
            encode(public.ST_AsEWKB(geom, 'NDR'), 'hex') AS geometry_wkb,
            source_fields::text AS source_fields
            FROM watergeo.hydrology_station WHERE snapshot_id=:id
            ORDER BY station_id COLLATE "C"
        """,
        """SELECT measure_id, station_id, source_uri, parameter, unit_name, period,
            source_fields::text AS source_fields
            FROM watergeo.hydrology_measure WHERE snapshot_id=:id
            ORDER BY measure_id COLLATE "C"
        """,
        """SELECT measure_id, observed_at, value, source_fields::text AS source_fields
            FROM watergeo.hydrology_latest_observation WHERE snapshot_id=:id
            ORDER BY measure_id COLLATE "C"
        """,
    )
    actual = []
    for statement, expected_rows in zip(statements, expected, strict=True):
        rows = [
            dict(row) for row in connection.execute(text(statement), {"id": snapshot_id}).mappings()
        ]
        if len(rows) != len(expected_rows):
            raise HydrologyError("Existing snapshot stored content mismatch")
        actual.append(
            [{**row, "source_fields": _source_json(row["source_fields"])} for row in rows]
        )
    expected_json = [
        [
            {
                **row,
                "source_fields": _source_json(json.dumps(row["source_fields"], allow_nan=False)),
            }
            for row in rows
        ]
        for rows in expected
    ]
    # Normalization sorts ASCII publisher IDs; explicit C collation gives the same
    # ordering for stored rows. This digest is recomputed, never trusted from a row.
    if digest(_canonical(actual)) != digest(_canonical(expected_json)):
        raise HydrologyError("Existing snapshot stored content mismatch")
