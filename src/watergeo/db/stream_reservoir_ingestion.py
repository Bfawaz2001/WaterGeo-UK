"""Atomic insert-only publication and exact retry verification for Stream reservoirs."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from watergeo.ingestion.stream_reservoir_client import read_snapshot
from watergeo.ingestion.stream_reservoirs import (
    EDITION,
    ITEM_ID,
    VERSION,
    NormalizedReservoirs,
    StreamReservoirError,
)


def verify_stored(connection: Connection, identity: UUID, expected: NormalizedReservoirs) -> None:
    metadata = (
        connection.execute(
            text("SELECT * FROM watergeo.stream_reservoir_snapshot WHERE id=:id"),
            {"id": identity},
        )
        .mappings()
        .one()
    )
    reservoirs = [
        dict(row)
        for row in connection.execute(
            text("""
                SELECT reservoir_id,name,latitude,longitude,capacity,capacity_unit
                FROM watergeo.stream_reservoir WHERE snapshot_id=:id
                ORDER BY reservoir_id COLLATE "C"
            """),
            {"id": identity},
        ).mappings()
    ]
    readings = [
        {
            **dict(row),
            "observed_at": row["observed_at"].isoformat(),
        }
        for row in connection.execute(
            text("""
                SELECT reservoir_id,observed_at,current_level,current_level_unit,
                    current_percentage,publisher_object_id,source_fields
                FROM watergeo.stream_reservoir_level WHERE snapshot_id=:id
                ORDER BY reservoir_id COLLATE "C",observed_at,publisher_object_id
            """),
            {"id": identity},
        ).mappings()
    ]
    reconstructed = NormalizedReservoirs(reservoirs, readings)
    manifest = metadata["manifest"]
    if (
        metadata["source_item_id"] != ITEM_ID
        or metadata["edition"] != EDITION
        or metadata["normalization_version"] != VERSION
        or metadata["normalized_sha256"] != expected.sha256
        or reconstructed.sha256 != expected.sha256
        or metadata["reservoir_count"] != len(reservoirs)
        or metadata["reading_count"] != len(readings)
        or manifest.get("content_sha256") != metadata["content_sha256"]
        or manifest.get("normalized_sha256") != expected.sha256
    ):
        raise StreamReservoirError("Stored Stream snapshot content mismatch")
    time_fields = {
        "retrieval_started_at": metadata["retrieval_started_at"],
        "retrieval_completed_at": metadata["retrieval_completed_at"],
        "source_item_created_ms": metadata["source_item_created_at"],
        "source_item_modified_ms": metadata["source_item_modified_at"],
    }
    for key, stored in time_fields.items():
        source = (
            datetime.fromtimestamp(manifest[key] / 1000, UTC)
            if key.endswith("_ms")
            else datetime.fromisoformat(manifest[key])
        )
        if source != stored:
            raise StreamReservoirError("Stored Stream snapshot time mismatch")


def load_snapshot(engine: Engine, directory: Path) -> dict[str, Any]:
    manifest, data = read_snapshot(directory)
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 7)"))
        existing = connection.execute(
            text("""
                SELECT id FROM watergeo.stream_reservoir_snapshot
                WHERE content_sha256=:hash AND normalization_version=:version
            """),
            {"hash": manifest["content_sha256"], "version": VERSION},
        ).scalar_one_or_none()
        if existing is not None:
            verify_stored(connection, existing, data)
            return {
                "status": "existing",
                "snapshot_id": str(existing),
                "reservoir_count": len(data.reservoirs),
                "reading_count": len(data.readings),
            }

        identity = uuid4()
        connection.execute(
            text("""
                INSERT INTO watergeo.stream_reservoir_snapshot
                    (id,source_item_id,edition,source_item_created_at,source_item_modified_at,
                     retrieval_started_at,retrieval_completed_at,content_sha256,
                     normalized_sha256,normalization_version,reservoir_count,reading_count,manifest)
                VALUES (:id,:item,:edition,:created,:modified,:started,:completed,:content,
                    :normalized,:version,:reservoirs,:readings,CAST(:manifest AS jsonb))
            """),
            {
                "id": identity,
                "item": ITEM_ID,
                "edition": EDITION,
                "created": datetime.fromtimestamp(manifest["source_item_created_ms"] / 1000, UTC),
                "modified": datetime.fromtimestamp(manifest["source_item_modified_ms"] / 1000, UTC),
                "started": manifest["retrieval_started_at"],
                "completed": manifest["retrieval_completed_at"],
                "content": manifest["content_sha256"],
                "normalized": data.sha256,
                "version": VERSION,
                "reservoirs": len(data.reservoirs),
                "readings": len(data.readings),
                "manifest": json.dumps(manifest),
            },
        )
        connection.execute(
            text("""
                INSERT INTO watergeo.stream_reservoir
                    (snapshot_id,reservoir_id,name,latitude,longitude,geom,capacity,capacity_unit)
                VALUES (:snapshot_id,:reservoir_id,:name,:latitude,:longitude,
                    public.ST_SetSRID(public.ST_MakePoint(:longitude,:latitude),4326),
                    :capacity,:capacity_unit)
            """),
            [{**row, "snapshot_id": identity} for row in data.reservoirs],
        )
        connection.execute(
            text("""
                INSERT INTO watergeo.stream_reservoir_level
                    (snapshot_id,reservoir_id,observed_at,current_level,current_level_unit,
                     current_percentage,publisher_object_id,source_fields)
                VALUES (:snapshot_id,:reservoir_id,:observed_at,:current_level,
                    :current_level_unit,:current_percentage,:publisher_object_id,
                    CAST(:source_fields AS jsonb))
            """),
            [
                {**row, "snapshot_id": identity, "source_fields": json.dumps(row["source_fields"])}
                for row in data.readings
            ],
        )
        verify_stored(connection, identity, data)
    return {
        "status": "inserted",
        "snapshot_id": str(identity),
        "reservoir_count": len(data.reservoirs),
        "reading_count": len(data.readings),
    }
