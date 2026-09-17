"""Synthetic geometry/provenance only; no publisher records or coordinates.

Each test rolls back its writes. The module also works independently of the
migration round-trip suite, against an explicitly opted-in disposable database.
"""

import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from watergeo.core.config import MigrationSettings, Settings
from watergeo.db.engine import create_database_engine

SQUARE = "POLYGON((0 0,10 0,10 10,0 10,0 0))"
MULTIPOLYGON = "MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)))"
SOURCE_FIELDS = {
    "ID": 7,
    "COMPANY": "Synthetic Dŵr Test",
    "Date Grant": None,
    "AreaType": "Synthetic contradictory sewerage label",
    "Licence": "Synthetic fixture under the repository MIT licence",
    "WARNINGS": "Synthetic warning; preserve verbatim",
    "LastUpdate": "2024-04-25",
}


@pytest.fixture(scope="module")
def writer() -> Iterator[Engine]:
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_database_engine(MigrationSettings())
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def connection(writer: Engine) -> Iterator[Connection]:
    with writer.connect() as connection, connection.begin() as transaction:
        yield connection
        transaction.rollback()


def insert_snapshot(
    connection: Connection, *, checksum: str = "a" * 64, transformation: str = "synthetic-v1"
) -> UUID:
    return connection.execute(
        text("""
            INSERT INTO watergeo.water_supply_snapshot
                (source_sha256, source_url, source_bytes, retrieved_at, publisher,
                 distributor, licence_name, licence_url, attribution, transformation_version)
            VALUES (:checksum, 'https://example.invalid/synthetic.zip', 123,
                    '2026-09-17T12:00:00Z', 'Synthetic publisher', 'Synthetic distributor',
                    'MIT', 'https://example.invalid/licence', 'Synthetic test fixture',
                    :transformation)
            RETURNING id
        """),
        {"checksum": checksum, "transformation": transformation},
    ).scalar_one()


def insert_area(
    connection: Connection,
    snapshot_id: UUID,
    *,
    wkt: str | None = SQUARE,
    srid: int = 27700,
    source_id: int = 7,
) -> None:
    connection.execute(
        text("""
            INSERT INTO watergeo.water_supply_area
                (snapshot_id, source_id, source_fields, geom)
            VALUES (:snapshot_id, :source_id, CAST(:fields AS jsonb),
                    ST_Multi(ST_GeomFromText(:wkt, :srid)))
        """),
        {
            "snapshot_id": snapshot_id,
            "source_id": source_id,
            "fields": json.dumps({**SOURCE_FIELDS, "ID": source_id}),
            "wkt": wkt,
            "srid": srid,
        },
    )


@pytest.mark.parametrize(
    "wkt",
    [
        SQUARE,
        MULTIPOLYGON,
        "POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 4,4 4,4 2,2 2))",
        "MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)),((4 4,6 4,6 6,4 6,4 4)))",
    ],
    ids=["polygon", "multipolygon", "hole", "disjoint-parts"],
)
def test_preserves_valid_geometry_and_source_fields(connection: Connection, wkt: str) -> None:
    snapshot_id = insert_snapshot(connection)
    insert_area(connection, snapshot_id, wkt=wkt)
    row = connection.execute(
        text("""
            SELECT source_fields, ST_GeometryType(geom) AS kind, ST_SRID(geom) AS srid,
                   ST_AsEWKB(geom) = ST_AsEWKB(ST_Multi(ST_GeomFromText(:wkt, 27700)))
                       AS unchanged
            FROM watergeo.water_supply_area WHERE snapshot_id = :snapshot_id
        """),
        {"wkt": wkt, "snapshot_id": snapshot_id},
    ).one()
    assert row.source_fields == SOURCE_FIELDS
    assert row.kind == "ST_MultiPolygon"
    assert row.srid == 27700
    assert row.unchanged  # Wrapping a Polygon must not repair/reorder/round its coordinates.


@pytest.mark.parametrize(
    ("wkt", "srid", "constraint"),
    [
        ("POLYGON((0 0,10 10,0 10,10 0,0 0))", 27700, "valid"),
        (
            "POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 8,8 8,8 2,2 2),(3 3,3 4,4 4,4 3,3 3))",
            27700,
            "valid",
        ),
        ("MULTIPOLYGON EMPTY", 27700, "not_empty"),
        ("POINT(1 2)", 27700, "type"),
        ("LINESTRING(0 0,1 1)", 27700, "type"),
        (SQUARE, 4326, "srid"),
        (SQUARE, 0, "srid"),
        ("POLYGON Z((0 0 0,10 0 0,10 10 0,0 10 0,0 0 0))", 27700, "dimensions"),
    ],
    ids=[
        "self-intersection",
        "nested-holes",
        "empty",
        "point",
        "line",
        "wrong-crs",
        "unknown-crs",
        "3d",
    ],
)
def test_rejects_unacceptable_geometry(
    connection: Connection, wkt: str, srid: int, constraint: str
) -> None:
    snapshot_id = insert_snapshot(connection)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_area(connection, snapshot_id, wkt=wkt, srid=srid)
    assert error.value.orig.sqlstate == "23514"
    assert error.value.orig.diag.constraint_name == f"water_supply_area_geometry_{constraint}"


def test_rejects_null_geometry(connection: Connection) -> None:
    snapshot_id = insert_snapshot(connection)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_area(connection, snapshot_id, wkt=None)
    assert error.value.orig.sqlstate == "23502"


def test_source_ids_are_scoped_to_snapshots(connection: Connection) -> None:
    first = insert_snapshot(connection)
    second = insert_snapshot(connection, checksum="b" * 64)
    insert_area(connection, first)
    insert_area(connection, second)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_area(connection, first)
    assert error.value.orig.sqlstate == "23505"
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_area(connection, UUID(int=0))
    assert error.value.orig.sqlstate == "23503"
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(
            text("DELETE FROM watergeo.water_supply_snapshot WHERE id = :id"), {"id": first}
        )
    assert error.value.orig.sqlstate == "23503"  # History is not cascade-deleted.


def test_snapshot_identity_includes_transformation_version(connection: Connection) -> None:
    insert_snapshot(connection)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_snapshot(connection)
    assert error.value.orig.sqlstate == "23505"
    insert_snapshot(connection, transformation="synthetic-v2")


@pytest.mark.parametrize("checksum", ["", "a" * 63, "G" * 64])
def test_rejects_invalid_archive_fingerprint(connection: Connection, checksum: str) -> None:
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        insert_snapshot(connection, checksum=checksum)
    assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE watergeo.water_supply_snapshot SET attribution = ' ' WHERE id = :id",
        "UPDATE watergeo.water_supply_snapshot SET source_bytes = 0 WHERE id = :id",
        "UPDATE watergeo.water_supply_snapshot SET licence_version = '' WHERE id = :id",
        "UPDATE watergeo.water_supply_area SET source_fields = '[]' WHERE snapshot_id = :id",
    ],
    ids=["missing-credit", "zero-bytes", "empty-licence-version", "non-object-fields"],
)
def test_rejects_incomplete_provenance(connection: Connection, statement: str) -> None:
    snapshot_id = insert_snapshot(connection)
    insert_area(connection, snapshot_id)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(text(statement), {"id": snapshot_id})
    assert error.value.orig.sqlstate == "23514"


def test_unknown_licence_version_is_not_invented(connection: Connection) -> None:
    snapshot_id = insert_snapshot(connection)
    row = connection.execute(
        text("""
            SELECT licence_version, retrieved_at, ingested_at
            FROM watergeo.water_supply_snapshot WHERE id = :id
        """),
        {"id": snapshot_id},
    ).one()
    assert row.licence_version is None
    assert row.retrieved_at.tzinfo is not None
    assert row.ingested_at.tzinfo is not None


def test_overlaps_remain_distinct_and_boundary_points_can_match(connection: Connection) -> None:
    snapshot_id = insert_snapshot(connection)
    insert_area(connection, snapshot_id)
    insert_area(connection, snapshot_id, source_id=8)
    ids = (
        connection.execute(
            text("""
            SELECT source_id FROM watergeo.water_supply_area
            WHERE snapshot_id = :id AND ST_Covers(geom, ST_SetSRID(ST_Point(0, 5), 27700))
            ORDER BY source_id
        """),
            {"id": snapshot_id},
        )
        .scalars()
        .all()
    )
    assert ids == [7, 8]  # Validity is per feature; overlapping areas are not deduplicated.


def test_invalid_area_rolls_back_whole_snapshot(writer: Engine) -> None:
    snapshot_id = None
    with pytest.raises(IntegrityError), writer.begin() as connection:
        snapshot_id = insert_snapshot(connection)
        insert_area(connection, snapshot_id)
        insert_area(connection, snapshot_id, source_id=8, wkt="POLYGON EMPTY")
    with writer.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM watergeo.water_supply_snapshot WHERE id = :id"),
                {"id": snapshot_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM watergeo.water_supply_area WHERE snapshot_id = :id"),
                {"id": snapshot_id},
            ).scalar_one()
            == 0
        )


def test_runtime_can_read_but_cannot_write_new_tables(writer: Engine) -> None:
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ WRITE"))
            connection.execute(text("SELECT id FROM watergeo.water_supply_snapshot LIMIT 1"))
            connection.execute(text("SELECT source_id FROM watergeo.water_supply_area LIMIT 1"))
            for statement in (
                "DELETE FROM watergeo.water_supply_snapshot",
                "DELETE FROM watergeo.water_supply_area",
            ):
                with pytest.raises(DBAPIError) as error, connection.begin_nested():
                    connection.execute(text(statement))
                assert error.value.orig.sqlstate == "42501"
    finally:
        engine.dispose()
