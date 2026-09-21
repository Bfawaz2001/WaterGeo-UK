"""Atomic, insert-only Environment Agency Water Quality publication."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text

from watergeo.db.water_quality_integrity import verify_stored_content
from watergeo.ingestion.water_quality import (
    VERSION,
    WaterQualityError,
)
from watergeo.ingestion.water_quality_client import read_snapshot


def load_snapshot(
    engine: Engine,
    directory: Path,
) -> dict[str, Any]:
    manifest, data = read_snapshot(directory)
    counts = data.counts

    with engine.begin() as connection:
        # Separate namespace from Hydrology and Catchment publication.
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 5)"))

        existing = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        normalized_sha256,
                        sampling_point_count,
                        sampling_point_with_location_count,
                        sampling_point_without_location_count
                    FROM watergeo.water_quality_snapshot
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
                raise WaterQualityError("Existing water-quality snapshot normalization mismatch")

            stored_counts = {
                "sampling_point_count": existing["sampling_point_count"],
                "sampling_point_with_location_count": existing[
                    "sampling_point_with_location_count"
                ],
                "sampling_point_without_location_count": existing[
                    "sampling_point_without_location_count"
                ],
            }

            if stored_counts != counts:
                raise WaterQualityError("Existing water-quality snapshot count mismatch")

            actual_count = connection.execute(
                text("""
                    SELECT count(*)
                    FROM watergeo.water_quality_sampling_point
                    WHERE snapshot_id = :id
                """),
                {"id": existing["id"]},
            ).scalar_one()

            if actual_count != len(data.sampling_points):
                raise WaterQualityError("Existing water-quality snapshot is incomplete")

            verify_stored_content(
                connection,
                existing["id"],
                data,
            )

            return {
                "status": "existing",
                "snapshot_id": str(existing["id"]),
                **counts,
            }

        previous = connection.execute(
            text("""
                SELECT
                    sampling_point_with_location_count
                    ::double precision
                    / sampling_point_count
                FROM watergeo.water_quality_snapshot
                WHERE normalization_version = :version
                ORDER BY
                    retrieval_completed_at DESC,
                    id DESC
                LIMIT 1
            """),
            {"version": VERSION},
        ).scalar_one_or_none()

        fraction = counts["sampling_point_with_location_count"] / counts["sampling_point_count"]

        if previous is not None and fraction < previous - 0.01:
            raise WaterQualityError(
                "Spatial completeness fell by over one percentage point; review source"
            )

        snapshot_id = uuid4()

        connection.execute(
            text("""
                INSERT INTO watergeo.water_quality_snapshot (
                    id,
                    content_sha256,
                    normalized_sha256,
                    normalization_version,
                    retrieval_started_at,
                    retrieval_completed_at,
                    manifest,
                    sampling_point_count,
                    sampling_point_with_location_count,
                    sampling_point_without_location_count
                )
                VALUES (
                    :id,
                    :content_sha256,
                    :normalized_sha256,
                    :normalization_version,
                    :retrieval_started_at,
                    :retrieval_completed_at,
                    CAST(:manifest AS jsonb),
                    :sampling_point_count,
                    :sampling_point_with_location_count,
                    :sampling_point_without_location_count
                )
            """),
            {
                "id": snapshot_id,
                "content_sha256": manifest["content_sha256"],
                "normalized_sha256": data.sha256,
                "normalization_version": VERSION,
                "retrieval_started_at": manifest["retrieval_started_at"],
                "retrieval_completed_at": manifest["retrieval_completed_at"],
                "manifest": json.dumps(
                    manifest,
                    allow_nan=False,
                ),
                **counts,
            },
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.water_quality_sampling_point (
                    snapshot_id,
                    sampling_point_id,
                    source_uri,
                    alt_label,
                    pref_label,
                    latitude,
                    longitude,
                    geom,
                    status,
                    sampling_point_type,
                    region,
                    area,
                    sub_area,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :sampling_point_id,
                    :source_uri,
                    :alt_label,
                    :pref_label,
                    :latitude,
                    :longitude,
                    CASE
                        WHEN CAST(:latitude AS double precision)
                            IS NULL
                        THEN NULL
                        ELSE public.ST_SetSRID(
                            public.ST_MakePoint(
                                :longitude,
                                :latitude
                            ),
                            4326
                        )
                    END,
                    CAST(:status AS jsonb),
                    CAST(:sampling_point_type AS jsonb),
                    CAST(:region AS jsonb),
                    CAST(:area AS jsonb),
                    CAST(:sub_area AS jsonb),
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    **row,
                    "snapshot_id": snapshot_id,
                    "status": (
                        json.dumps(
                            row["status"],
                            allow_nan=False,
                        )
                        if row["status"] is not None
                        else None
                    ),
                    "sampling_point_type": (
                        json.dumps(
                            row["sampling_point_type"],
                            allow_nan=False,
                        )
                        if row["sampling_point_type"] is not None
                        else None
                    ),
                    "region": (
                        json.dumps(
                            row["region"],
                            allow_nan=False,
                        )
                        if row["region"] is not None
                        else None
                    ),
                    "area": (
                        json.dumps(
                            row["area"],
                            allow_nan=False,
                        )
                        if row["area"] is not None
                        else None
                    ),
                    "sub_area": (
                        json.dumps(
                            row["sub_area"],
                            allow_nan=False,
                        )
                        if row["sub_area"] is not None
                        else None
                    ),
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.sampling_points
            ],
        )

    return {
        "status": "inserted",
        "snapshot_id": str(snapshot_id),
        **counts,
    }
