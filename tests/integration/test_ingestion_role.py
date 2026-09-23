"""Integration coverage for the least-privilege canonical-ingestion role."""

import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine


@pytest.fixture(scope="module")
def ingestion_engine() -> Iterator[Engine]:
    command.upgrade(
        Config("alembic.ini"),
        "head",
    )

    engine = create_database_engine(
        IngestionSettings(),
    )

    try:
        yield engine
    finally:
        engine.dispose()


def test_ingestion_role_is_least_privilege(
    ingestion_engine: Engine,
) -> None:
    with ingestion_engine.connect() as connection:
        role = connection.execute(
            text("""
                SELECT
                    current_user,
                    rolsuper,
                    rolcreatedb,
                    rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user
            """)
        ).one()

        assert role.current_user == "watergeo_ingest"
        assert role.rolsuper is False
        assert role.rolcreatedb is False
        assert role.rolcreaterole is False

        assert connection.execute(
            text("""
                SELECT has_schema_privilege(
                    current_user,
                    'watergeo',
                    'USAGE'
                )
            """)
        ).scalar_one()

        assert not connection.execute(
            text("""
                SELECT has_schema_privilege(
                    current_user,
                    'watergeo',
                    'CREATE'
                )
            """)
        ).scalar_one()

        for table in (
            "water_supply_snapshot",
            "water_supply_area",
            "water_supply_area_transformation",
            "water_quality_snapshot",
            "water_quality_sampling_point",
            "water_quality_observation_retrieval",
            "water_quality_observation_unit",
            "water_quality_observation",
            "stream_reservoir_snapshot",
            "stream_reservoir",
            "stream_reservoir_level",
        ):
            assert connection.execute(
                text("""
                    SELECT has_table_privilege(
                        current_user,
                        :table_name,
                        'SELECT'
                    )
                """),
                {
                    "table_name": (f"watergeo.{table}"),
                },
            ).scalar_one()

            assert connection.execute(
                text("""
                    SELECT has_table_privilege(
                        current_user,
                        :table_name,
                        'INSERT'
                    )
                """),
                {
                    "table_name": (f"watergeo.{table}"),
                },
            ).scalar_one()

            assert not connection.execute(
                text("""
                    SELECT has_table_privilege(
                        current_user,
                        :table_name,
                        'UPDATE'
                    )
                """),
                {
                    "table_name": (f"watergeo.{table}"),
                },
            ).scalar_one()

            assert not connection.execute(
                text("""
                    SELECT has_table_privilege(
                        current_user,
                        :table_name,
                        'DELETE'
                    )
                """),
                {
                    "table_name": (f"watergeo.{table}"),
                },
            ).scalar_one()


def test_ingestion_role_can_insert_complete_snapshot_shape(
    ingestion_engine: Engine,
) -> None:
    with (
        ingestion_engine.connect() as connection,
        connection.begin() as transaction,
    ):
        snapshot_id = connection.execute(
            text("""
                INSERT INTO watergeo.water_supply_snapshot (
                    source_sha256,
                    source_url,
                    source_bytes,
                    retrieved_at,
                    publisher,
                    distributor,
                    licence_name,
                    licence_version,
                    licence_url,
                    attribution,
                    transformation_version
                )
                VALUES (
                    :source_sha256,
                    :source_url,
                    :source_bytes,
                    :retrieved_at,
                    :publisher,
                    :distributor,
                    :licence_name,
                    NULL,
                    :licence_url,
                    :attribution,
                    :transformation_version
                )
                RETURNING id
            """),
            {
                "source_sha256": "e" * 64,
                "source_url": ("https://example.invalid/integration-source.zip"),
                "source_bytes": 123,
                "retrieved_at": ("2026-09-18T00:00:00+00:00"),
                "publisher": ("Synthetic integration publisher"),
                "distributor": ("Synthetic integration distributor"),
                "licence_name": "Synthetic licence",
                "licence_url": ("https://example.invalid/licence"),
                "attribution": ("Synthetic integration fixture"),
                "transformation_version": ("integration-ingestion-role-v1"),
            },
        ).scalar_one()

        assert isinstance(
            snapshot_id,
            UUID,
        )

        connection.execute(
            text("""
                INSERT INTO watergeo.water_supply_area (
                    snapshot_id,
                    source_id,
                    source_fields,
                    geom
                )
                VALUES (
                    :snapshot_id,
                    1,
                    CAST(:source_fields AS jsonb),
                    public.ST_Multi(
                        public.ST_GeomFromText(
                            :wkt,
                            27700
                        )
                    )
                )
            """),
            {
                "snapshot_id": snapshot_id,
                "source_fields": json.dumps(
                    {
                        "ID": 1,
                        "fixture": ("synthetic integration"),
                    }
                ),
                "wkt": ("POLYGON((0 0,10 0,10 10,0 10,0 0))"),
            },
        )

        connection.execute(
            text("""
                INSERT INTO
                    watergeo.water_supply_area_transformation (
                        snapshot_id,
                        source_id,
                        transformation_id,
                        method,
                        keep_collapsed,
                        shapely_version,
                        geos_version,
                        invalid_reason,
                        source_decoded_wkb_sha256,
                        canonical_wkb_sha256,
                        review_status,
                        review_reason,
                        review_reference,
                        details
                    )
                VALUES (
                    :snapshot_id,
                    1,
                    :transformation_id,
                    :method,
                    false,
                    :shapely_version,
                    :geos_version,
                    :invalid_reason,
                    :source_hash,
                    :canonical_hash,
                    :review_status,
                    :review_reason,
                    :review_reference,
                    CAST(:details AS jsonb)
                )
            """),
            {
                "snapshot_id": snapshot_id,
                "transformation_id": ("synthetic-reviewed-v1"),
                "method": "synthetic",
                "shapely_version": "synthetic",
                "geos_version": "synthetic",
                "invalid_reason": ("Synthetic integration fixture"),
                "source_hash": "a" * 64,
                "canonical_hash": "b" * 64,
                "review_status": "approved",
                "review_reason": ("Synthetic integration fixture"),
                "review_reference": ("tests/integration/test_ingestion_role.py"),
                "details": json.dumps(
                    {
                        "fixture": True,
                    }
                ),
            },
        )

        counts = connection.execute(
            text("""
                SELECT
                    (
                        SELECT count(*)
                        FROM watergeo.water_supply_snapshot
                        WHERE id = :snapshot_id
                    ) AS snapshots,
                    (
                        SELECT count(*)
                        FROM watergeo.water_supply_area
                        WHERE snapshot_id = :snapshot_id
                    ) AS areas,
                    (
                        SELECT count(*)
                        FROM
                            watergeo
                            .water_supply_area_transformation
                        WHERE snapshot_id = :snapshot_id
                    ) AS transformations
            """),
            {
                "snapshot_id": snapshot_id,
            },
        ).one()

        assert counts.snapshots == 1
        assert counts.areas == 1
        assert counts.transformations == 1

        with (
            pytest.raises(DBAPIError) as update_error,
            connection.begin_nested(),
        ):
            connection.execute(
                text("""
                    UPDATE watergeo.water_supply_snapshot
                    SET attribution = 'forbidden'
                    WHERE id = :snapshot_id
                """),
                {
                    "snapshot_id": snapshot_id,
                },
            )

        assert update_error.value.orig.sqlstate == "42501"

        with (
            pytest.raises(DBAPIError) as delete_error,
            connection.begin_nested(),
        ):
            connection.execute(
                text("""
                    DELETE FROM
                        watergeo
                        .water_supply_area_transformation
                    WHERE snapshot_id = :snapshot_id
                """),
                {
                    "snapshot_id": snapshot_id,
                },
            )

        assert delete_error.value.orig.sqlstate == "42501"

        transaction.rollback()
