"""Disposable PostGIS verification with synthetic official-shaped evidence only."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import DBAPIError

from watergeo.api.app import create_app
from watergeo.core.config import IngestionSettings, MigrationSettings, Settings
from watergeo.db.engine import create_database_engine
from watergeo.db.hydrology_ingestion import load_snapshot
from watergeo.ingestion.hydrology import LICENCE
from watergeo.ingestion.hydrology_client import fetch_snapshot, read_snapshot


@pytest.fixture(scope="module")
def engines() -> Iterator[tuple[Engine, Engine, Engine]]:
    command.upgrade(Config("alembic.ini"), "head")
    engines = (
        create_database_engine(IngestionSettings()),
        create_database_engine(Settings()),
        create_database_engine(MigrationSettings()),
    )
    yield engines
    for engine in engines:
        engine.dispose()


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    records = json.loads(Path("tests/fixtures/hydrology/records.json").read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        kind = {"stations": "stations", "measures": "measures", "readings": "observations"}[
            request.url.path.rsplit("/", 1)[1]
        ]
        return httpx.Response(
            200,
            json={
                "meta": {
                    "publisher": "Environment Agency",
                    "license": LICENCE,
                    "version": "2.1.1",
                    "limit": 30000,
                },
                "items": records[kind],
            },
        )

    return fetch_snapshot(tmp_path, transport=httpx.MockTransport(respond))


@pytest.fixture
def loaded(engines: tuple[Engine, Engine, Engine], bundle: Path) -> Iterator[dict[str, Any]]:
    result = load_snapshot(engines[0], bundle)
    yield result
    with engines[2].begin() as connection:
        for statement in (
            "DELETE FROM watergeo.hydrology_latest_observation WHERE snapshot_id=:id",
            "DELETE FROM watergeo.hydrology_measure WHERE snapshot_id=:id",
            "DELETE FROM watergeo.hydrology_station WHERE snapshot_id=:id",
            "DELETE FROM watergeo.hydrology_snapshot WHERE id=:id",
        ):
            connection.execute(text(statement), {"id": result["snapshot_id"]})


def test_atomic_insert_idempotence_geometry_and_indexes(
    engines: tuple[Engine, Engine, Engine], bundle: Path, loaded: dict[str, Any]
) -> None:
    assert loaded["status"] == "inserted"
    assert load_snapshot(engines[0], bundle) == {**loaded, "status": "existing"}
    with engines[1].connect() as connection:
        rows = connection.execute(
            text(
                "SELECT station_id,ST_SRID(geom),ST_AsText(geom) "
                "FROM watergeo.hydrology_station WHERE snapshot_id=:id ORDER BY station_id"
            ),
            {"id": loaded["snapshot_id"]},
        ).all()
        assert rows == [
            ("a", 4326, "POINT(-1 52)"),
            ("b", 4326, "POINT(-1 52)"),
            ("unlocated", None, None),
        ]
        index = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='watergeo' "
                "AND indexname='hydrology_station_geography'"
            )
        ).scalar_one()
        assert "gist" in index and "geography" in index and "IS NOT NULL" in index


def test_station_http_list_detail_near_freshness(loaded: dict[str, Any]) -> None:
    with TestClient(create_app()) as client:
        dataset = client.get("/v1/hydrology/dataset")
        assert dataset.status_code == 200
        data = dataset.json()
        assert data["station_count"] == 3
        assert data["station_without_location_count"] == 1
        assert data["licence"] == "Open Government Licence v3"
        page = client.get("/v1/hydrology/stations?limit=2").json()
        assert [s["station_id"] for s in page["items"]] == ["a", "b"]
        page2 = client.get(
            "/v1/hydrology/stations",
            params={"after_id": page["next_after_id"], "snapshot_id": data["snapshot_id"]},
        ).json()
        assert [s["station_id"] for s in page2["items"]] == ["unlocated"]
        detail = client.get("/v1/hydrology/stations/unlocated")
        assert detail.status_code == 200
        assert detail.json()["geometry"] is None
        assert detail.json()["location_status"] == "unavailable"
        assert detail.json()["measures"][0]["latest_observation"]["value"] == 2.5
        assert detail.json()["measures"][0]["latest_observation"]["observed_at"].startswith("2020-")
        assert (
            client.get("/v1/hydrology/stations/a").json()["measures"][0]["latest_observation"][
                "value"
            ]
            == 0
        )
        assert (
            client.get("/v1/hydrology/stations/b").json()["measures"][0]["latest_observation"][
                "value"
            ]
            is None
        )
        near = client.get(
            "/v1/hydrology/stations/near", params={"lon": -1, "lat": 52, "radius_m": 10}
        )
        assert near.status_code == 200
        assert [(s["station_id"], s["distance_m"]) for s in near.json()["items"]] == [
            ("a", 0),
            ("b", 0),
        ]
        assert near.json()["spatial_exclusion_note"]
        assert (
            client.get("/v1/hydrology/stations/near?lon=0&lat=0&radius_m=1").json()["items"] == []
        )
        assert client.get("/v1/hydrology/stations/unknown").status_code == 404
        assert dataset.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "latitude,longitude,wkt",
    [
        (52, None, "POINT(-1 52)"),
        (None, None, "POINT(-1 52)"),
        (52, -1, None),
        (91, 0, "POINT(0 91)"),
        (52, -1, "POINT(0 52)"),
        (float("nan"), 0, "POINT(0 52)"),
    ],
)
def test_location_database_constraints(
    engines: tuple[Engine, Engine, Engine],
    loaded: dict[str, Any],
    latitude: float | None,
    longitude: float | None,
    wkt: str | None,
) -> None:
    with pytest.raises(DBAPIError), engines[0].begin() as connection:
        connection.execute(
            text("""INSERT INTO watergeo.hydrology_station
            (snapshot_id,station_id,source_uri,labels,latitude,longitude,geom,source_fields)
            VALUES (:id,'bad','synthetic:bad','[]',:lat,:lon,ST_GeomFromText(:wkt,4326),'{}')"""),
            {"id": loaded["snapshot_id"], "lat": latitude, "lon": longitude, "wkt": wkt},
        )


def test_failure_after_station_insert_rolls_back(
    engines: tuple[Engine, Engine, Engine], bundle: Path
) -> None:
    manifest, _ = read_snapshot(bundle)

    def fail(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if "INSERT INTO watergeo.hydrology_measure" in statement:
            raise RuntimeError("injected after station insertion")

    event.listen(engines[0], "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            load_snapshot(engines[0], bundle)
    finally:
        event.remove(engines[0], "before_cursor_execute", fail)
    with engines[1].connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM watergeo.hydrology_snapshot WHERE content_sha256=:hash"),
                {"hash": manifest["content_sha256"]},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM watergeo.hydrology_station")).scalar_one()
            == 0
        )


def test_measure_and_observation_foreign_keys(
    engines: tuple[Engine, Engine, Engine], loaded: dict[str, Any]
) -> None:
    statements = [
        """INSERT INTO watergeo.hydrology_measure
        (snapshot_id,measure_id,station_id,source_uri,parameter,unit_name,period,source_fields)
        VALUES (:id,'orphan','absent','synthetic:orphan','flow','m3/s',900,'{}')""",
        """INSERT INTO watergeo.hydrology_latest_observation
        (snapshot_id,measure_id,observed_at,value,source_fields)
        VALUES (:id,'orphan',now(),0,'{}')""",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError) as error, engines[0].begin() as connection:
            connection.execute(text(statement), {"id": loaded["snapshot_id"]})
        assert error.value.orig.sqlstate == "23503"


def test_exact_role_privileges(
    engines: tuple[Engine, Engine, Engine], loaded: dict[str, Any]
) -> None:
    tables = [
        "hydrology_snapshot",
        "hydrology_station",
        "hydrology_measure",
        "hydrology_latest_observation",
    ]
    for engine, can_insert in [(engines[0], True), (engines[1], False)]:
        with engine.connect() as connection:
            assert not connection.execute(
                text("SELECT has_schema_privilege(current_user,'watergeo','CREATE')")
            ).scalar_one()
            for table in tables:
                for privilege, allowed in [
                    ("SELECT", True),
                    ("INSERT", can_insert),
                    ("UPDATE", False),
                    ("DELETE", False),
                    ("TRUNCATE", False),
                ]:
                    assert (
                        connection.execute(
                            text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                            {"table": "watergeo." + table, "privilege": privilege},
                        ).scalar_one()
                        is allowed
                    )
        for statement in [
            "UPDATE watergeo.hydrology_snapshot SET station_count=0",
            "DELETE FROM watergeo.hydrology_latest_observation",
        ]:
            with pytest.raises(DBAPIError) as error, engine.begin() as connection:
                connection.execute(text("SET TRANSACTION READ WRITE"))
                connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"


def test_empty_dataset_fails_closed(engines: tuple[Engine, Engine, Engine]) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/hydrology/dataset")
        assert response.status_code == 503
        assert response.json() == {"detail": "Hydrology dataset unavailable"}


def test_spatial_completeness_degradation_requires_review(
    engines: tuple[Engine, Engine, Engine],
    loaded: dict[str, Any],
    tmp_path: Path,
) -> None:
    records = json.loads(Path("tests/fixtures/hydrology/records.json").read_text())
    records["stations"][0].pop("lat")
    records["stations"][0].pop("long")

    def respond(request: httpx.Request) -> httpx.Response:
        kind = {"stations": "stations", "measures": "measures", "readings": "observations"}[
            request.url.path.rsplit("/", 1)[1]
        ]
        return httpx.Response(
            200,
            json={
                "meta": {
                    "publisher": "Environment Agency",
                    "license": LICENCE,
                    "version": "2.1.1",
                    "limit": 30000,
                },
                "items": records[kind],
            },
        )

    path = fetch_snapshot(tmp_path, transport=httpx.MockTransport(respond))
    with pytest.raises(ValueError, match="Spatial completeness"):
        load_snapshot(engines[0], path)
    with engines[1].connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM watergeo.hydrology_snapshot")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize(
    "mutation,inspection,expected",
    [
        (
            "UPDATE watergeo.hydrology_station SET labels='[\"changed\"]' "
            "WHERE snapshot_id=:id AND station_id='a'",
            "SELECT labels FROM watergeo.hydrology_station "
            "WHERE snapshot_id=:id AND station_id='a'",
            ["changed"],
        ),
        (
            "UPDATE watergeo.hydrology_measure SET unit_name='changed' "
            "WHERE snapshot_id=:id AND station_id='a'",
            "SELECT unit_name FROM watergeo.hydrology_measure "
            "WHERE snapshot_id=:id AND station_id='a'",
            "changed",
        ),
        (
            "UPDATE watergeo.hydrology_latest_observation SET value=123 "
            "WHERE snapshot_id=:id AND measure_id='a-flow-i-900-m3s-qualified'",
            "SELECT value FROM watergeo.hydrology_latest_observation "
            "WHERE snapshot_id=:id AND measure_id='a-flow-i-900-m3s-qualified'",
            123,
        ),
        (
            "UPDATE watergeo.hydrology_station SET source_fields='{}' "
            "WHERE snapshot_id=:id AND station_id='a'",
            "SELECT source_fields FROM watergeo.hydrology_station "
            "WHERE snapshot_id=:id AND station_id='a'",
            {},
        ),
        (
            "UPDATE watergeo.hydrology_measure SET source_fields='{}' "
            "WHERE snapshot_id=:id AND station_id='a'",
            "SELECT source_fields FROM watergeo.hydrology_measure "
            "WHERE snapshot_id=:id AND station_id='a'",
            {},
        ),
        (
            "UPDATE watergeo.hydrology_latest_observation SET source_fields='{}' "
            "WHERE snapshot_id=:id AND measure_id='a-flow-i-900-m3s-qualified'",
            "SELECT source_fields FROM watergeo.hydrology_latest_observation "
            "WHERE snapshot_id=:id AND measure_id='a-flow-i-900-m3s-qualified'",
            {},
        ),
    ],
)
def test_retry_rejects_stored_child_corruption(
    engines: tuple[Engine, Engine, Engine],
    bundle: Path,
    loaded: dict[str, Any],
    mutation: str,
    inspection: str,
    expected: Any,
) -> None:
    from watergeo.ingestion.hydrology import HydrologyError

    assert load_snapshot(engines[0], bundle)["status"] == "existing"
    params = {"id": loaded["snapshot_id"]}
    with engines[2].begin() as connection:
        assert connection.execute(text(mutation), params).rowcount == 1
    with pytest.raises(HydrologyError, match="stored content mismatch"):
        load_snapshot(engines[0], bundle)
    with engines[1].connect() as connection:
        assert connection.execute(text(inspection), params).scalar_one() == expected
        assert (
            connection.execute(
                text("SELECT count(*) FROM watergeo.hydrology_snapshot")
            ).scalar_one()
            == 1
        )
        counts = connection.execute(
            text("""
            SELECT (SELECT count(*) FROM watergeo.hydrology_station WHERE snapshot_id=:id),
                   (SELECT count(*) FROM watergeo.hydrology_measure WHERE snapshot_id=:id),
                   (SELECT count(*) FROM watergeo.hydrology_latest_observation
                    WHERE snapshot_id=:id)
        """),
            params,
        ).one()
        assert tuple(counts) == (3, 3, 3)


def test_history_insert_retry_and_stored_corruption_detection(
    engines: tuple[Engine, Engine, Engine],
    tmp_path: Path,
    loaded: dict[str, Any],
) -> None:
    from datetime import UTC, datetime

    import httpx2 as httpx

    from watergeo.db.hydrology_history_ingestion import load_history
    from watergeo.ingestion.hydrology import LICENCE, HydrologyError
    from watergeo.ingestion.hydrology_history_client import fetch_history

    with engines[1].connect() as connection:
        measure_id = connection.execute(
            text("""
                SELECT measure_id
                FROM watergeo.hydrology_measure
                WHERE snapshot_id = :snapshot_id
                ORDER BY measure_id COLLATE "C"
                LIMIT 1
            """),
            {"snapshot_id": loaded["snapshot_id"]},
        ).scalar_one()

    measure_uri = "http://environment.data.gov.uk/hydrology/id/measures/" + measure_id

    rows = [
        {
            "measure": {"@id": measure_uri},
            "date": "2026-09-19",
            "dateTime": "2026-09-19T00:00:00",
            "value": 0,
            "quality": "Unchecked",
        },
        {
            "measure": {"@id": measure_uri},
            "date": "2026-09-19",
            "dateTime": "2026-09-19T00:15:00",
            "quality": "Missing",
        },
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "meta": {
                    "publisher": "Environment Agency",
                    "license": LICENCE,
                    "licenseName": "OGL 3",
                    "version": "2.1.1",
                    "limit": 5000,
                },
                "items": rows,
            },
            headers={"content-type": "application/json"},
        )

    bundle = fetch_history(
        measure_id,
        datetime(2026, 9, 19, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 19, 1, 0, tzinfo=UTC),
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    inserted = load_history(engines[0], bundle)

    assert inserted["status"] == "inserted"
    assert inserted["record_count"] == 2

    existing = load_history(engines[0], bundle)

    assert existing == {
        **inserted,
        "status": "existing",
    }

    params = {"id": inserted["retrieval_id"]}

    with engines[2].begin() as connection:
        assert (
            connection.execute(
                text("""
                    UPDATE watergeo.hydrology_historical_observation
                    SET value = 123
                    WHERE retrieval_id = :id
                      AND observed_at = '2026-09-19T00:00:00Z'
                """),
                params,
            ).rowcount
            == 1
        )

    with pytest.raises(
        HydrologyError,
        match="stored content mismatch",
    ):
        load_history(engines[0], bundle)

    with engines[2].begin() as connection:
        connection.execute(
            text("""
                DELETE FROM watergeo.hydrology_historical_observation
                WHERE retrieval_id = :id
            """),
            params,
        )
        connection.execute(
            text("""
                DELETE FROM watergeo.hydrology_history_retrieval
                WHERE id = :id
            """),
            params,
        )


def test_history_unknown_measure_fails_closed(
    engines: tuple[Engine, Engine, Engine],
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    import httpx2 as httpx

    from watergeo.db.hydrology_history_ingestion import load_history
    from watergeo.ingestion.hydrology import LICENCE, HydrologyError
    from watergeo.ingestion.hydrology_history_client import fetch_history

    measure_id = "unknown-level-i-900-m-qualified"
    measure_uri = "http://environment.data.gov.uk/hydrology/id/measures/" + measure_id

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "meta": {
                    "publisher": "Environment Agency",
                    "license": LICENCE,
                    "licenseName": "OGL 3",
                    "version": "2.1.1",
                    "limit": 5000,
                },
                "items": [
                    {
                        "measure": {"@id": measure_uri},
                        "date": "2026-09-19",
                        "dateTime": "2026-09-19T00:00:00",
                        "value": 1,
                        "quality": "Unchecked",
                    }
                ],
            },
            headers={"content-type": "application/json"},
        )

    bundle = fetch_history(
        measure_id,
        datetime(2026, 9, 19, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 19, 1, 0, tzinfo=UTC),
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(
        HydrologyError,
        match="unknown measure",
    ):
        load_history(engines[0], bundle)


def test_history_http_explicit_retrieval_pagination(
    engines: tuple[Engine, Engine, Engine],
    tmp_path: Path,
    loaded: dict[str, Any],
) -> None:
    from datetime import UTC, datetime

    import httpx2 as httpx

    from watergeo.db.hydrology_history_ingestion import load_history
    from watergeo.ingestion.hydrology import LICENCE
    from watergeo.ingestion.hydrology_history_client import fetch_history

    with engines[1].connect() as connection:
        measure_id = connection.execute(
            text("""
                SELECT measure_id
                FROM watergeo.hydrology_measure
                WHERE snapshot_id = :snapshot_id
                ORDER BY measure_id COLLATE "C"
                LIMIT 1
            """),
            {"snapshot_id": loaded["snapshot_id"]},
        ).scalar_one()

    measure_uri = "http://environment.data.gov.uk/hydrology/id/measures/" + measure_id

    rows = [
        {
            "measure": {"@id": measure_uri},
            "date": "2026-09-19",
            "dateTime": "2026-09-19T00:00:00",
            "value": 0,
            "quality": "Unchecked",
        },
        {
            "measure": {"@id": measure_uri},
            "date": "2026-09-19",
            "dateTime": "2026-09-19T00:15:00",
            "value": 1,
            "quality": "Unchecked",
        },
        {
            "measure": {"@id": measure_uri},
            "date": "2026-09-19",
            "dateTime": "2026-09-19T00:30:00",
            "quality": "Missing",
        },
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "meta": {
                    "publisher": "Environment Agency",
                    "license": LICENCE,
                    "licenseName": "OGL 3",
                    "version": "2.1.1",
                    "limit": 5000,
                },
                "items": rows,
            },
            headers={"content-type": "application/json"},
        )

    bundle = fetch_history(
        measure_id,
        datetime(2026, 9, 19, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 19, 1, 0, tzinfo=UTC),
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    history = load_history(engines[0], bundle)

    try:
        with TestClient(create_app()) as client:
            first = client.get(
                f"/v1/hydrology/history/{history['retrieval_id']}",
                params={"limit": 2},
            )

            assert first.status_code == 200
            body = first.json()

            assert body["record_count"] == 3
            assert body["measure_id"] == measure_id
            assert len(body["observations"]) == 2
            assert body["observations"][0]["value"] == 0
            assert body["next_after"] is not None
            assert first.headers["cache-control"] == "no-store"

            second = client.get(
                f"/v1/hydrology/history/{history['retrieval_id']}",
                params={
                    "limit": 2,
                    "after": body["next_after"],
                },
            )

            assert second.status_code == 200
            second_body = second.json()

            assert len(second_body["observations"]) == 1
            assert second_body["observations"][0]["value"] is None
            assert second_body["next_after"] is None

            missing = client.get("/v1/hydrology/history/00000000-0000-0000-0000-000000000000")
            assert missing.status_code == 404

            naive = client.get(
                f"/v1/hydrology/history/{history['retrieval_id']}",
                params={"after": "2026-09-19T00:00:00"},
            )
            assert naive.status_code == 422

    finally:
        params = {"id": history["retrieval_id"]}

        with engines[2].begin() as connection:
            connection.execute(
                text("""
                    DELETE FROM watergeo.hydrology_historical_observation
                    WHERE retrieval_id = :id
                """),
                params,
            )
            connection.execute(
                text("""
                    DELETE FROM watergeo.hydrology_history_retrieval
                    WHERE id = :id
                """),
                params,
            )
