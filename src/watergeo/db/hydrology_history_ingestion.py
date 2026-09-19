"""Atomic append-only publication of verified hydrology history evidence."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text

from watergeo.db.hydrology_history_integrity import verify_stored_history
from watergeo.ingestion.hydrology import HydrologyError
from watergeo.ingestion.hydrology_history import VERSION
from watergeo.ingestion.hydrology_history_client import read_history


def load_history(
    engine: Engine,
    directory: Path,
) -> dict[str, Any]:
    manifest, data = read_history(directory)

    with engine.begin() as connection:
        # Separate advisory namespace from latest-snapshot publication.
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 3)"))

        # Historical retrieval must refer to a publisher measure previously
        # accepted by the reviewed hydrology metadata ingestion.
        known_measure = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM watergeo.hydrology_measure
                    WHERE measure_id = :measure_id
                )
            """),
            {"measure_id": data.measure_id},
        ).scalar_one()

        if not known_measure:
            raise HydrologyError("Historical retrieval references unknown measure")

        existing = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        normalized_sha256,
                        record_count
                    FROM watergeo.hydrology_history_retrieval
                    WHERE content_sha256 = :content_sha256
                      AND normalization_version = :version
                """),
                {
                    "content_sha256": manifest["content_sha256"],
                    "version": VERSION,
                },
            )
            .mappings()
            .first()
        )

        if existing:
            if existing["normalized_sha256"] != data.sha256:
                raise HydrologyError("Existing history retrieval normalization mismatch")

            if existing["record_count"] != data.record_count:
                raise HydrologyError("Existing history retrieval is incomplete")

            verify_stored_history(
                connection,
                existing["id"],
                data,
            )

            return {
                "status": "existing",
                "retrieval_id": str(existing["id"]),
                "measure_id": data.measure_id,
                "record_count": data.record_count,
            }

        retrieval_id = uuid4()

        connection.execute(
            text("""
                INSERT INTO watergeo.hydrology_history_retrieval (
                    id,
                    measure_id,
                    requested_from,
                    requested_to,
                    retrieval_started_at,
                    retrieval_completed_at,
                    content_sha256,
                    normalized_sha256,
                    normalization_version,
                    record_count,
                    manifest
                )
                VALUES (
                    :id,
                    :measure_id,
                    :requested_from,
                    :requested_to,
                    :retrieval_started_at,
                    :retrieval_completed_at,
                    :content_sha256,
                    :normalized_sha256,
                    :normalization_version,
                    :record_count,
                    CAST(:manifest AS jsonb)
                )
            """),
            {
                "id": retrieval_id,
                "measure_id": data.measure_id,
                "requested_from": manifest["requested_from"],
                "requested_to": manifest["requested_to"],
                "retrieval_started_at": manifest["retrieval_started_at"],
                "retrieval_completed_at": manifest["retrieval_completed_at"],
                "content_sha256": manifest["content_sha256"],
                "normalized_sha256": data.sha256,
                "normalization_version": VERSION,
                "record_count": data.record_count,
                "manifest": json.dumps(manifest),
            },
        )

        if data.observations:
            connection.execute(
                text("""
                    INSERT INTO watergeo.hydrology_historical_observation (
                        retrieval_id,
                        measure_id,
                        observed_at,
                        value,
                        source_fields
                    )
                    VALUES (
                        :retrieval_id,
                        :measure_id,
                        :observed_at,
                        :value,
                        CAST(:source_fields AS jsonb)
                    )
                """),
                [
                    {
                        **row,
                        "retrieval_id": retrieval_id,
                        "source_fields": json.dumps(row["source_fields"]),
                    }
                    for row in data.observations
                ],
            )

    return {
        "status": "inserted",
        "retrieval_id": str(retrieval_id),
        "measure_id": data.measure_id,
        "record_count": data.record_count,
    }
