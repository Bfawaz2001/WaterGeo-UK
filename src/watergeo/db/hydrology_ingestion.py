"""Atomic, insert-only hydrology publication from verified local evidence."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text

from watergeo.ingestion.hydrology import VERSION, HydrologyError
from watergeo.ingestion.hydrology_client import read_snapshot


def load_snapshot(engine: Engine, directory: Path) -> dict[str, Any]:
    manifest, data = read_snapshot(directory)
    counts = data.counts
    with engine.begin() as connection:
        # Serialize publication/no-op decisions without UPDATE or broad privileges.
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 2)"))
        existing = (
            connection.execute(
                text("""
            SELECT id, normalized_sha256 FROM watergeo.hydrology_snapshot
            WHERE content_sha256 = :hash AND normalization_version = :version
        """),
                {"hash": manifest["content_sha256"], "version": VERSION},
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["normalized_sha256"] != data.sha256:
                raise HydrologyError("Existing snapshot normalization mismatch")
            actual = connection.execute(
                text("""
                SELECT (SELECT count(*) FROM watergeo.hydrology_station WHERE snapshot_id=:id) AS s,
                    (SELECT count(*) FROM watergeo.hydrology_measure WHERE snapshot_id=:id) AS m,
                    (SELECT count(*) FROM watergeo.hydrology_latest_observation WHERE
                    snapshot_id=:id) AS o
            """),
                {"id": existing["id"]},
            ).one()
            if tuple(actual) != (len(data.stations), len(data.measures), len(data.observations)):
                raise HydrologyError("Existing snapshot is incomplete")
            return {"status": "existing", "snapshot_id": str(existing["id"]), **counts}
        previous = connection.execute(
            text("""
            SELECT station_with_location_count::double precision / station_count AS fraction
            FROM watergeo.hydrology_snapshot WHERE normalization_version = :version
            ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1
        """),
            {"version": VERSION},
        ).scalar_one_or_none()
        fraction = counts["station_with_location_count"] / counts["station_count"]
        if previous is not None and fraction < previous - 0.01:
            raise HydrologyError(
                "Spatial completeness fell by over one percentage point; review source"
            )
        sid = uuid4()
        connection.execute(
            text("""
            INSERT INTO watergeo.hydrology_snapshot
            (id, content_sha256, normalized_sha256, normalization_version, retrieval_started_at,
             retrieval_completed_at, manifest, station_count, station_with_location_count,
             station_without_location_count, measure_count, latest_observation_count)
            VALUES (:id, :content, :normalized, :version, :started, :completed, CAST(:manifest
            AS jsonb),
                    :station_count, :station_with_location_count, :station_without_location_count,
                    :measure_count, :latest_observation_count)
        """),
            {
                "id": sid,
                "content": manifest["content_sha256"],
                "normalized": data.sha256,
                "version": VERSION,
                "started": manifest["retrieval_started_at"],
                "completed": manifest["retrieval_completed_at"],
                "manifest": json.dumps(manifest),
                **counts,
            },
        )
        connection.execute(
            text("""
            INSERT INTO watergeo.hydrology_station
                (snapshot_id, station_id, source_uri, labels, latitude, longitude, geom,
                source_fields)
            VALUES (:snapshot_id, :station_id, :source_uri, CAST(:labels AS jsonb), :latitude,
            :longitude,
                CASE WHEN CAST(:latitude AS double precision) IS NULL THEN NULL
                    ELSE public.ST_SetSRID(public.ST_MakePoint(:longitude, :latitude),4326) END,
                CAST(:source_fields AS jsonb))
        """),
            [
                {
                    **row,
                    "snapshot_id": sid,
                    "labels": json.dumps(row["labels"]),
                    "source_fields": json.dumps(row["source_fields"]),
                }
                for row in data.stations
            ],
        )
        connection.execute(
            text("""
            INSERT INTO watergeo.hydrology_measure
                (snapshot_id, measure_id, station_id, source_uri, parameter, unit_name, period,
                source_fields)
            VALUES (:snapshot_id, :measure_id, :station_id, :source_uri, :parameter, :unit_name,
            :period,
                    CAST(:source_fields AS jsonb))
        """),
            [
                {**row, "snapshot_id": sid, "source_fields": json.dumps(row["source_fields"])}
                for row in data.measures
            ],
        )
        if data.observations:
            connection.execute(
                text("""
                INSERT INTO watergeo.hydrology_latest_observation
                    (snapshot_id, measure_id, observed_at, value, source_fields)
                VALUES (:snapshot_id, :measure_id, :observed_at, :value, CAST(:source_fields AS
                jsonb))
            """),
                [
                    {**row, "snapshot_id": sid, "source_fields": json.dumps(row["source_fields"])}
                    for row in data.observations
                ],
            )
    return {"status": "inserted", "snapshot_id": str(sid), **counts}
