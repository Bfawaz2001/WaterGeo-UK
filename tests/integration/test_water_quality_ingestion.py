"""Disposable PostGIS verification for EA Water Quality sampling points."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from watergeo.core.config import (
    IngestionSettings,
    MigrationSettings,
)
from watergeo.db.engine import create_database_engine
from watergeo.db.water_quality_ingestion import load_snapshot
from watergeo.ingestion.water_quality import WaterQualityError

EVIDENCE = Path(
    "data/raw/environment-agency/water-quality/sampling-points/d362e6ec-19c3-47a7-8e5c-0c9a336dce91"
)


@pytest.fixture(scope="module")
def engines() -> Iterator[tuple[Engine, Engine]]:
    command.upgrade(
        Config("alembic.ini"),
        "head",
    )

    engines = (
        create_database_engine(
            IngestionSettings(),
            statement_timeout_ms=120000,
        ),
        create_database_engine(
            MigrationSettings(),
            statement_timeout_ms=120000,
        ),
    )

    yield engines

    for engine in engines:
        engine.dispose()


@pytest.fixture(scope="module")
def loaded(
    engines: tuple[Engine, Engine],
) -> dict[str, object]:
    if not (EVIDENCE / "manifest.json").exists():
        pytest.skip("Reviewed local Water Quality evidence bundle is not available")

    return load_snapshot(
        engines[0],
        EVIDENCE,
    )


def test_water_quality_snapshot_loads_atomically(
    engines: tuple[Engine, Engine],
    loaded: dict[str, object],
) -> None:
    assert loaded["status"] in {"inserted", "existing"}
    assert loaded["sampling_point_count"] == 66300
    assert loaded["sampling_point_with_location_count"] == 66300
    assert loaded["sampling_point_without_location_count"] == 0

    with engines[1].connect() as connection:
        row = connection.execute(
            text("""
                SELECT
                    sampling_point_count,
                    sampling_point_with_location_count,
                    sampling_point_without_location_count,
                    normalized_sha256
                FROM watergeo.water_quality_snapshot
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": loaded["snapshot_id"]},
        ).one()

        assert row.sampling_point_count == 66300
        assert row.sampling_point_with_location_count == 66300
        assert row.sampling_point_without_location_count == 0
        assert row.normalized_sha256 == (
            "21433969c0803233499c76e336af0e03a9335de6fdd28f44b9ebbaaa1b8c2d9f"
        )

        point_count = connection.execute(
            text("""
                SELECT count(*)
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id = CAST(:id AS uuid)
            """),
            {"id": loaded["snapshot_id"]},
        ).scalar_one()

        assert point_count == 66300


def test_water_quality_exact_retry_is_verified_noop(
    engines: tuple[Engine, Engine],
    loaded: dict[str, object],
) -> None:
    again = load_snapshot(
        engines[0],
        EVIDENCE,
    )

    assert again["status"] == "existing"
    assert again["snapshot_id"] == loaded["snapshot_id"]


def test_water_quality_unusual_publisher_ids_are_preserved(
    engines: tuple[Engine, Engine],
    loaded: dict[str, object],
) -> None:
    with engines[1].connect() as connection:
        rows = (
            connection.execute(
                text("""
                SELECT sampling_point_id
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id = CAST(:id AS uuid)
                  AND sampling_point_id IN (
                      'AN-B BOOTH',
                      'AN-CORBY  I',
                      'MD-GWW20/01',
                      'NW-GWW08/02'
                  )
                ORDER BY sampling_point_id COLLATE "C"
            """),
                {"id": loaded["snapshot_id"]},
            )
            .scalars()
            .all()
        )

    assert rows == [
        "AN-B BOOTH",
        "AN-CORBY  I",
        "MD-GWW20/01",
        "NW-GWW08/02",
    ]


def test_water_quality_geometry_matches_source_coordinates(
    engines: tuple[Engine, Engine],
    loaded: dict[str, object],
) -> None:
    with engines[1].connect() as connection:
        row = connection.execute(
            text("""
                SELECT
                    latitude,
                    longitude,
                    public.ST_Y(geom) AS geom_latitude,
                    public.ST_X(geom) AS geom_longitude,
                    public.ST_SRID(geom) AS srid
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id = CAST(:id AS uuid)
                  AND sampling_point_id = 'AN-011262'
            """),
            {"id": loaded["snapshot_id"]},
        ).one()

    assert row.latitude == 52.0473
    assert row.longitude == -1.192
    assert row.geom_latitude == row.latitude
    assert row.geom_longitude == row.longitude
    assert row.srid == 4326


def test_water_quality_exact_retry_detects_stored_tampering(
    engines: tuple[Engine, Engine],
    loaded: dict[str, object],
) -> None:
    migration_engine = engines[1]

    with migration_engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE watergeo.water_quality_sampling_point
                SET pref_label = 'tampered'
                WHERE snapshot_id = CAST(:id AS uuid)
                  AND sampling_point_id = 'AN-011262'
            """),
            {"id": loaded["snapshot_id"]},
        )

    try:
        with pytest.raises(
            WaterQualityError,
            match="stored content mismatch",
        ):
            load_snapshot(
                engines[0],
                EVIDENCE,
            )
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE watergeo.water_quality_sampling_point
                    SET pref_label =
                        'STEANE PARK THE MANOR HOUSE STW'
                    WHERE snapshot_id = CAST(:id AS uuid)
                      AND sampling_point_id = 'AN-011262'
                """),
                {"id": loaded["snapshot_id"]},
            )
