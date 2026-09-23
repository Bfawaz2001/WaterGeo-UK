"""Atomic insert-only observation publication and exact stored-content retry verification."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from watergeo.ingestion.water_quality import VERSION as POINT_VERSION
from watergeo.ingestion.water_quality import WaterQualityError
from watergeo.ingestion.water_quality_observation_client import read_observations
from watergeo.ingestion.water_quality_observations import VERSION, Normalized, Scope


def verify_stored(connection: Connection, identity: UUID, expected: Normalized) -> None:
    metadata = (
        connection.execute(
            text("""
        SELECT * FROM watergeo.water_quality_observation_retrieval WHERE id=:id
    """),
            {"id": identity},
        )
        .mappings()
        .one()
    )
    scope = Scope(
        metadata["sampling_point_id"],
        metadata["determinand_notation"],
        metadata["date_from"],
        metadata["date_to"],
    )
    units = list(
        connection.execute(
            text("""
        SELECT source_fields FROM watergeo.water_quality_observation_unit
        WHERE retrieval_id=:id ORDER BY notation COLLATE "C"
    """),
            {"id": identity},
        ).scalars()
    )
    rows = [
        dict(row)
        for row in connection.execute(
            text(
                """SELECT observation_id, sampling_point_id, sample_id, sampling_id,
                    observed_at_text, determinand_notation, unit_notation, result_text,
                    numeric_value,
                    upper_bound, lower_bound, source_fields
                    FROM watergeo.water_quality_observation
                    WHERE retrieval_id=:id ORDER BY observation_id COLLATE "C"
                """
            ),
            {"id": identity},
        ).mappings()
    ]
    reconstructed = Normalized(scope, metadata["determinand"], units, rows)
    if (
        metadata["normalization_version"] != VERSION
        or metadata["normalized_sha256"] != expected.sha256
        or reconstructed.sha256 != expected.sha256
        or metadata["record_count"] != len(rows)
    ):
        raise WaterQualityError("Stored observation retrieval content mismatch")
    manifest = metadata["manifest"]
    if (
        manifest.get("scope") != scope.as_dict()
        or manifest.get("content_sha256") != metadata["content_sha256"]
        or manifest.get("normalized_sha256") != expected.sha256
    ):
        raise WaterQualityError("Stored observation manifest mismatch")
    for key in ("retrieval_started_at", "retrieval_completed_at"):
        if datetime.fromisoformat(manifest[key]) != metadata[key]:
            raise WaterQualityError("Stored observation retrieval time mismatch")


def load_observations(engine: Engine, directory: Path) -> dict[str, Any]:
    manifest, data = read_observations(directory)
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 6)"))
        existing = connection.execute(
            text("""
            SELECT id FROM watergeo.water_quality_observation_retrieval
            WHERE content_sha256=:hash AND normalization_version=:version
        """),
            {"hash": manifest["content_sha256"], "version": VERSION},
        ).scalar_one_or_none()
        if existing is not None:
            verify_stored(connection, existing, data)
            return {
                "status": "existing",
                "retrieval_id": str(existing),
                "record_count": len(data.observations),
            }
        point_snapshot = connection.execute(
            text("""
            SELECT s.id FROM watergeo.water_quality_snapshot s
            JOIN watergeo.water_quality_sampling_point p ON p.snapshot_id=s.id
            WHERE p.sampling_point_id=:point AND s.normalization_version=:version
            ORDER BY s.retrieval_completed_at DESC, s.id DESC LIMIT 1
        """),
            {"point": data.scope.sampling_point_id, "version": POINT_VERSION},
        ).scalar_one_or_none()
        if point_snapshot is None:
            raise WaterQualityError("Observation retrieval references an unknown sampling point")
        identity = uuid4()
        connection.execute(
            text("""
            INSERT INTO watergeo.water_quality_observation_retrieval
                (id, sampling_point_snapshot_id, sampling_point_id, determinand_notation,
                 date_from, date_to, retrieval_started_at, retrieval_completed_at,
                 content_sha256, normalized_sha256, normalization_version, record_count,
                 determinand, manifest)
            VALUES (:id, :snapshot, :point, :determinand_notation, :date_from, :date_to,
                :started, :completed, :hash, :normalized, :version, :count,
                CAST(:determinand AS jsonb), CAST(:manifest AS jsonb))
        """),
            {
                "id": identity,
                "snapshot": point_snapshot,
                "point": data.scope.sampling_point_id,
                "determinand_notation": data.scope.determinand,
                "date_from": data.scope.date_from,
                "date_to": data.scope.date_to,
                "started": manifest["retrieval_started_at"],
                "completed": manifest["retrieval_completed_at"],
                "hash": manifest["content_sha256"],
                "normalized": data.sha256,
                "version": VERSION,
                "count": len(data.observations),
                "determinand": json.dumps(data.determinand, allow_nan=False),
                "manifest": json.dumps(manifest, allow_nan=False),
            },
        )
        if data.units:
            connection.execute(
                text("""
                INSERT INTO watergeo.water_quality_observation_unit
                    (retrieval_id, notation, source_fields)
                VALUES (:id, :notation, CAST(:fields AS jsonb))
            """),
                [
                    {
                        "id": identity,
                        "notation": unit["notation"],
                        "fields": json.dumps(unit, allow_nan=False),
                    }
                    for unit in data.units
                ],
            )
        if data.observations:
            connection.execute(
                text("""
                INSERT INTO watergeo.water_quality_observation
                    (retrieval_id, observation_id, sampling_point_id, sample_id, sampling_id,
                     observed_at_text, determinand_notation, unit_notation, result_text,
                     numeric_value, upper_bound, lower_bound, source_fields)
                VALUES (:id, :observation_id, :sampling_point_id, :sample_id, :sampling_id,
                    :observed_at_text, :determinand_notation, :unit_notation, :result_text,
                    :numeric_value, :upper_bound, :lower_bound, CAST(:source_fields AS jsonb))
            """),
                [
                    {
                        **row,
                        "id": identity,
                        "source_fields": json.dumps(row["source_fields"], allow_nan=False),
                    }
                    for row in data.observations
                ],
            )
        verify_stored(connection, identity, data)
    return {
        "status": "inserted",
        "retrieval_id": str(identity),
        "record_count": len(data.observations),
    }
