"""Atomic, insert-only Catchment Data Explorer snapshot publication."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text

from watergeo.db.catchment_integrity import verify_stored_content
from watergeo.ingestion.catchment_client import read_snapshot
from watergeo.ingestion.catchments import (
    PLAN_VERSION,
    VERSION,
    CatchmentError,
)


def load_snapshot(
    engine: Engine,
    directory: Path,
) -> dict[str, Any]:
    manifest, data = read_snapshot(directory)
    counts = data.counts

    with engine.begin() as connection:
        # Separate advisory-lock namespace from hydrology latest/history.
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 4)"))

        existing = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        normalized_sha256,
                        plan_version,
                        river_basin_district_count,
                        management_catchment_count,
                        operational_catchment_count,
                        water_body_count,
                        geometry_feature_count
                    FROM watergeo.catchment_snapshot
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
                raise CatchmentError("Existing catchment snapshot normalization mismatch")

            if existing["plan_version"] != PLAN_VERSION:
                raise CatchmentError("Existing catchment snapshot plan version mismatch")

            stored_counts = {
                "river_basin_district_count": existing["river_basin_district_count"],
                "management_catchment_count": existing["management_catchment_count"],
                "operational_catchment_count": existing["operational_catchment_count"],
                "water_body_count": existing["water_body_count"],
                "geometry_feature_count": existing["geometry_feature_count"],
            }

            if stored_counts != counts:
                raise CatchmentError("Existing catchment snapshot count mismatch")

            actual_counts = connection.execute(
                text("""
                    SELECT
                        (
                            SELECT count(*)
                            FROM watergeo.catchment_river_basin_district
                            WHERE snapshot_id = :id
                        ) AS rbd,
                        (
                            SELECT count(*)
                            FROM watergeo.catchment_management
                            WHERE snapshot_id = :id
                        ) AS management,
                        (
                            SELECT count(*)
                            FROM watergeo.catchment_operational
                            WHERE snapshot_id = :id
                        ) AS operational,
                        (
                            SELECT count(*)
                            FROM watergeo.catchment_water_body
                            WHERE snapshot_id = :id
                        ) AS water_body,
                        (
                            SELECT count(*)
                            FROM watergeo.catchment_water_body_geometry
                            WHERE snapshot_id = :id
                        ) AS geometry
                """),
                {"id": existing["id"]},
            ).one()

            if tuple(actual_counts) != (
                len(data.river_basin_districts),
                len(data.management_catchments),
                len(data.operational_catchments),
                len(data.water_bodies),
                len(data.geometries),
            ):
                raise CatchmentError("Existing catchment snapshot is incomplete")

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

        snapshot_id = uuid4()

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_snapshot (
                    id,
                    plan_version,
                    retrieval_started_at,
                    retrieval_completed_at,
                    content_sha256,
                    normalized_sha256,
                    normalization_version,
                    river_basin_district_count,
                    management_catchment_count,
                    operational_catchment_count,
                    water_body_count,
                    geometry_feature_count,
                    manifest
                )
                VALUES (
                    :id,
                    :plan_version,
                    :retrieval_started_at,
                    :retrieval_completed_at,
                    :content_sha256,
                    :normalized_sha256,
                    :normalization_version,
                    :river_basin_district_count,
                    :management_catchment_count,
                    :operational_catchment_count,
                    :water_body_count,
                    :geometry_feature_count,
                    CAST(:manifest AS jsonb)
                )
            """),
            {
                "id": snapshot_id,
                "plan_version": PLAN_VERSION,
                "retrieval_started_at": manifest["retrieval_started_at"],
                "retrieval_completed_at": manifest["retrieval_completed_at"],
                "content_sha256": manifest["content_sha256"],
                "normalized_sha256": data.sha256,
                "normalization_version": VERSION,
                "manifest": json.dumps(
                    manifest,
                    allow_nan=False,
                ),
                **counts,
            },
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_river_basin_district (
                    snapshot_id,
                    river_basin_district_id,
                    name,
                    publisher_uri,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :river_basin_district_id,
                    :name,
                    :publisher_uri,
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    **row,
                    "snapshot_id": snapshot_id,
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.river_basin_districts
            ],
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_management (
                    snapshot_id,
                    management_catchment_id,
                    river_basin_district_id,
                    name,
                    publisher_uri,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :management_catchment_id,
                    :river_basin_district_id,
                    :name,
                    :publisher_uri,
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    **row,
                    "snapshot_id": snapshot_id,
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.management_catchments
            ],
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_operational (
                    snapshot_id,
                    operational_catchment_id,
                    management_catchment_id,
                    river_basin_district_id,
                    name,
                    publisher_uri,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :operational_catchment_id,
                    :management_catchment_id,
                    :river_basin_district_id,
                    :name,
                    :publisher_uri,
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    **row,
                    "snapshot_id": snapshot_id,
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.operational_catchments
            ],
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_water_body (
                    snapshot_id,
                    water_body_id,
                    operational_catchment_id,
                    management_catchment_id,
                    river_basin_district_id,
                    name,
                    water_body_type,
                    publisher_uri,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :water_body_id,
                    :operational_catchment_id,
                    :management_catchment_id,
                    :river_basin_district_id,
                    :name,
                    :water_body_type,
                    :publisher_uri,
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    **row,
                    "snapshot_id": snapshot_id,
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.water_bodies
            ],
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.catchment_water_body_geometry (
                    snapshot_id,
                    water_body_id,
                    feature_index,
                    geometry_type_uri,
                    geometry_kind,
                    geom,
                    source_fields
                )
                VALUES (
                    :snapshot_id,
                    :water_body_id,
                    :feature_index,
                    :geometry_type_uri,
                    :geometry_kind,
                    public.ST_SetSRID(
                        public.ST_GeomFromGeoJSON(:geometry),
                        4326
                    ),
                    CAST(:source_fields AS jsonb)
                )
            """),
            [
                {
                    "snapshot_id": snapshot_id,
                    "water_body_id": row["water_body_id"],
                    "feature_index": row["feature_index"],
                    "geometry_type_uri": row["geometry_type_uri"],
                    "geometry_kind": row["geometry_kind"],
                    "geometry": json.dumps(
                        row["geometry"],
                        allow_nan=False,
                    ),
                    "source_fields": json.dumps(
                        row["source_fields"],
                        allow_nan=False,
                    ),
                }
                for row in data.geometries
            ],
        )

    return {
        "status": "inserted",
        "snapshot_id": str(snapshot_id),
        **counts,
    }
