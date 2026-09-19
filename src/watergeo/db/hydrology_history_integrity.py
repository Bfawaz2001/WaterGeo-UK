"""Recompute historical-retrieval integrity from actual stored child rows."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, text

from watergeo.db.hydrology_integrity import _canonical, _source_json
from watergeo.ingestion.hydrology import HydrologyError, digest
from watergeo.ingestion.hydrology_history import NormalizedHistory


def verify_stored_history(
    connection: Connection,
    retrieval_id: UUID,
    data: NormalizedHistory,
) -> None:
    rows = [
        dict(row)
        for row in connection.execute(
            text("""
                SELECT
                    measure_id,
                    observed_at,
                    value,
                    source_fields::text AS source_fields
                FROM watergeo.hydrology_historical_observation
                WHERE retrieval_id = :id
                ORDER BY observed_at ASC
            """),
            {"id": retrieval_id},
        ).mappings()
    ]

    if len(rows) != len(data.observations):
        raise HydrologyError("Existing history retrieval stored content mismatch")

    actual = [
        {
            **row,
            "source_fields": _source_json(row["source_fields"]),
        }
        for row in rows
    ]

    expected = [
        {
            **row,
            "observed_at": datetime.fromisoformat(row["observed_at"]),
            "source_fields": _source_json(
                json.dumps(
                    row["source_fields"],
                    allow_nan=False,
                )
            ),
        }
        for row in data.observations
    ]

    if digest(_canonical(actual)) != digest(_canonical(expected)):
        raise HydrologyError("Existing history retrieval stored content mismatch")
