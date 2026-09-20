"""Disposable PostGIS verification for synthetic Cycle 3 catchment evidence."""

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

from watergeo.api.app import create_app, get_database
from watergeo.core.config import IngestionSettings, MigrationSettings, Settings
from watergeo.db.catchment_ingestion import load_snapshot
from watergeo.db.engine import create_database_engine
from watergeo.ingestion.catchment_client import fetch_snapshot
from watergeo.ingestion.catchments import CatchmentError


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


def _page(
    title: str,
    links: list[str],
) -> bytes:
    anchors = "".join(f'<a href="{href}">link</a>' for href in links)

    return (
        "<html><head>"
        f"<title>{title} | Catchment Data Explorer</title>"
        "</head><body>"
        f"{anchors}"
        "</body></html>"
    ).encode()


def _feature(
    water_body_id: str,
    *,
    name: str,
    water_body_type: str,
    geometry_kind: str,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "id": water_body_id,
            "name": name,
            "uri": (
                "http://environment.data.gov.uk/catchment-planning/so/WaterBody/" + water_body_id
            ),
            "water-body-type": {
                "string": water_body_type,
                "lang": "en",
            },
            "geometry-type": (
                "http://environment.data.gov.uk/catchment-planning/def/geometry/" + geometry_kind
            ),
        },
        "geometry": geometry,
    }


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    base = "https://environment.data.gov.uk/catchment-planning/v/c3-plan"

    responses: dict[str, tuple[str, bytes]] = {
        f"{base}": (
            "text/html",
            _page(
                "Cycle 3",
                [("/catchment-planning/v/c3-plan/RiverBasinDistrict/4")],
            ),
        ),
        f"{base}/RiverBasinDistrict/4": (
            "text/html",
            _page(
                "Synthetic RBD River Basin District",
                [("/catchment-planning/v/c3-plan/ManagementCatchment/3101")],
            ),
        ),
        f"{base}/ManagementCatchment/3101": (
            "text/html",
            _page(
                "Synthetic Management Management Catchment",
                [
                    ("/catchment-planning/v/c3-plan/RiverBasinDistrict/4"),
                    ("/catchment-planning/v/c3-plan/OperationalCatchment/3471"),
                ],
            ),
        ),
        f"{base}/OperationalCatchment/3471": (
            "text/html",
            _page(
                "Synthetic Operational Operational Catchment",
                [
                    ("/catchment-planning/v/c3-plan/RiverBasinDistrict/4"),
                    ("/catchment-planning/v/c3-plan/ManagementCatchment/3101"),
                    ("/catchment-planning/v/c3-plan/WaterBody/GBTEST001"),
                    ("/catchment-planning/v/c3-plan/WaterBody/GBTEST002"),
                ],
            ),
        ),
    }

    geojson = {
        "type": "FeatureCollection",
        "features": [
            _feature(
                "GBTEST001",
                name="Synthetic River",
                water_body_type="River",
                geometry_kind="Catchment",
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-2.0, 52.0],
                            [-1.9, 52.0],
                            [-1.9, 52.1],
                            [-2.0, 52.1],
                            [-2.0, 52.0],
                        ]
                    ],
                },
            ),
            _feature(
                "GBTEST001",
                name="Synthetic River",
                water_body_type="River",
                geometry_kind="RiverLine",
                geometry={
                    "type": "LineString",
                    "coordinates": [
                        [-1.99, 52.01],
                        [-1.95, 52.05],
                    ],
                },
            ),
            _feature(
                "GBTEST002",
                name="Synthetic Lake",
                water_body_type="Lake",
                geometry_kind="Catchment",
                geometry={
                    "type": "MultiPolygon",
                    "coordinates": [
                        [
                            [
                                [-2.2, 52.2],
                                [-2.1, 52.2],
                                [-2.1, 52.3],
                                [-2.2, 52.3],
                                [-2.2, 52.2],
                            ]
                        ]
                    ],
                },
            ),
            _feature(
                "GBTEST002",
                name="Synthetic Lake",
                water_body_type="Lake",
                geometry_kind="RiverLine",
                geometry={
                    "type": "MultiLineString",
                    "coordinates": [
                        [
                            [-2.19, 52.21],
                            [-2.15, 52.25],
                        ]
                    ],
                },
            ),
        ],
    }

    responses[f"{base}/RiverBasinDistrict/4.geojson"] = (
        "application/vnd.geo+json",
        json.dumps(geojson).encode(),
    )

    def respond(request: httpx.Request) -> httpx.Response:
        try:
            content_type, body = responses[str(request.url)]
        except KeyError:
            return httpx.Response(
                404,
                request=request,
            )

        return httpx.Response(
            200,
            headers={"content-type": content_type},
            content=body,
            request=request,
        )

    return fetch_snapshot(
        tmp_path,
        transport=httpx.MockTransport(respond),
        request_interval=0,
    )


@pytest.fixture
def loaded(
    engines: tuple[Engine, Engine, Engine],
    bundle: Path,
) -> Iterator[dict[str, Any]]:
    result = load_snapshot(engines[0], bundle)

    yield result

    with engines[2].begin() as connection:
        for statement in (
            ("DELETE FROM watergeo.catchment_water_body_geometry WHERE snapshot_id=:id"),
            ("DELETE FROM watergeo.catchment_water_body WHERE snapshot_id=:id"),
            ("DELETE FROM watergeo.catchment_operational WHERE snapshot_id=:id"),
            ("DELETE FROM watergeo.catchment_management WHERE snapshot_id=:id"),
            ("DELETE FROM watergeo.catchment_river_basin_district WHERE snapshot_id=:id"),
            ("DELETE FROM watergeo.catchment_snapshot WHERE id=:id"),
        ):
            connection.execute(
                text(statement),
                {"id": result["snapshot_id"]},
            )


def test_insert_retry_counts_and_all_geometry_types(
    engines: tuple[Engine, Engine, Engine],
    bundle: Path,
    loaded: dict[str, Any],
) -> None:
    assert loaded["status"] == "inserted"
    assert loaded["river_basin_district_count"] == 1
    assert loaded["management_catchment_count"] == 1
    assert loaded["operational_catchment_count"] == 1
    assert loaded["water_body_count"] == 2
    assert loaded["geometry_feature_count"] == 4

    assert load_snapshot(
        engines[0],
        bundle,
    ) == {
        **loaded,
        "status": "existing",
    }

    with engines[1].connect() as connection:
        geometries = connection.execute(
            text("""
                SELECT
                    water_body_id,
                    feature_index,
                    geometry_kind,
                    public.ST_GeometryType(geom),
                    public.ST_SRID(geom)
                FROM watergeo.catchment_water_body_geometry
                WHERE snapshot_id = :id
                ORDER BY
                    water_body_id COLLATE "C",
                    feature_index
            """),
            {"id": loaded["snapshot_id"]},
        ).all()

    assert geometries == [
        (
            "GBTEST001",
            0,
            "Catchment",
            "ST_Polygon",
            4326,
        ),
        (
            "GBTEST001",
            1,
            "RiverLine",
            "ST_LineString",
            4326,
        ),
        (
            "GBTEST002",
            2,
            "Catchment",
            "ST_MultiPolygon",
            4326,
        ),
        (
            "GBTEST002",
            3,
            "RiverLine",
            "ST_MultiLineString",
            4326,
        ),
    ]


def test_hierarchy_foreign_keys_are_preserved(
    engines: tuple[Engine, Engine, Engine],
    loaded: dict[str, Any],
) -> None:
    with engines[1].connect() as connection:
        rows = connection.execute(
            text("""
                SELECT
                    water_body_id,
                    operational_catchment_id,
                    management_catchment_id,
                    river_basin_district_id
                FROM watergeo.catchment_water_body
                WHERE snapshot_id = :id
                ORDER BY water_body_id COLLATE "C"
            """),
            {"id": loaded["snapshot_id"]},
        ).all()

    assert rows == [
        ("GBTEST001", "3471", "3101", "4"),
        ("GBTEST002", "3471", "3101", "4"),
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        (
            "UPDATE watergeo.catchment_water_body "
            "SET name='changed' "
            "WHERE snapshot_id=:id "
            "AND water_body_id='GBTEST001'"
        ),
        (
            "UPDATE watergeo.catchment_water_body_geometry "
            "SET source_fields='{}' "
            "WHERE snapshot_id=:id "
            "AND water_body_id='GBTEST001' "
            "AND feature_index=0"
        ),
        (
            "UPDATE watergeo.catchment_water_body_geometry "
            "SET geom=public.ST_SetSRID("
            "public.ST_GeomFromText("
            "'LINESTRING(-1 52,-1.1 52.1)'"
            "),4326) "
            "WHERE snapshot_id=:id "
            "AND water_body_id='GBTEST001' "
            "AND feature_index=1"
        ),
    ],
)
def test_retry_rejects_stored_child_corruption(
    engines: tuple[Engine, Engine, Engine],
    bundle: Path,
    loaded: dict[str, Any],
    mutation: str,
) -> None:
    assert load_snapshot(engines[0], bundle)["status"] == "existing"

    with engines[2].begin() as connection:
        assert (
            connection.execute(
                text(mutation),
                {"id": loaded["snapshot_id"]},
            ).rowcount
            == 1
        )

    with pytest.raises(
        CatchmentError,
        match="stored content mismatch",
    ):
        load_snapshot(
            engines[0],
            bundle,
        )


def test_failure_mid_load_rolls_back_everything(
    engines: tuple[Engine, Engine, Engine],
    bundle: Path,
) -> None:
    with engines[2].begin() as connection:
        connection.execute(text("DELETE FROM watergeo.catchment_water_body_geometry"))
        connection.execute(text("DELETE FROM watergeo.catchment_water_body"))
        connection.execute(text("DELETE FROM watergeo.catchment_operational"))
        connection.execute(text("DELETE FROM watergeo.catchment_management"))
        connection.execute(text("DELETE FROM watergeo.catchment_river_basin_district"))
        connection.execute(text("DELETE FROM watergeo.catchment_snapshot"))

    def fail(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if "INSERT INTO watergeo.catchment_operational" in statement:
            raise RuntimeError("injected catchment failure")

    event.listen(
        engines[0],
        "before_cursor_execute",
        fail,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="injected catchment failure",
        ):
            load_snapshot(
                engines[0],
                bundle,
            )
    finally:
        event.remove(
            engines[0],
            "before_cursor_execute",
            fail,
        )

    with engines[1].connect() as connection:
        counts = connection.execute(
            text("""
                SELECT
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_snapshot
                    ),
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_river_basin_district
                    ),
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_management
                    ),
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_operational
                    ),
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_water_body
                    ),
                    (
                        SELECT count(*)
                        FROM watergeo.catchment_water_body_geometry
                    )
            """)
        ).one()

    assert tuple(counts) == (0, 0, 0, 0, 0, 0)


def test_exact_role_privileges(
    engines: tuple[Engine, Engine, Engine],
) -> None:
    tables = [
        "catchment_snapshot",
        "catchment_river_basin_district",
        "catchment_management",
        "catchment_operational",
        "catchment_water_body",
        "catchment_water_body_geometry",
    ]

    for engine, can_insert in [
        (engines[0], True),
        (engines[1], False),
    ]:
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
                    actual = connection.execute(
                        text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                        {
                            "table": f"watergeo.{table}",
                            "privilege": privilege,
                        },
                    ).scalar_one()

                    assert actual is allowed


@pytest.fixture
def catchment_api(
    engines: tuple[Engine, Engine, Engine],
    loaded: dict[str, Any],
) -> Iterator[TestClient]:
    assert loaded["status"] == "inserted"

    app = create_app(Settings())
    app.dependency_overrides[get_database] = lambda: engines[1]

    with TestClient(app) as client:
        yield client


def test_public_catchment_dataset_contract(
    catchment_api: TestClient,
    loaded: dict[str, Any],
) -> None:
    response = catchment_api.get("/v1/catchments/dataset")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    body = response.json()

    assert body["snapshot_id"] == loaded["snapshot_id"]
    assert body["plan_version"] == "c3-plan"
    assert body["normalization_version"] == "ea-cde-c3-plan-v1"
    assert body["river_basin_district_count"] == 1
    assert body["management_catchment_count"] == 1
    assert body["operational_catchment_count"] == 1
    assert body["water_body_count"] == 2
    assert body["geometry_feature_count"] == 4

    assert body["hierarchy"] == (
        "River Basin District -> Management Catchment -> Operational Catchment -> Water Body"
    )

    assert "station-to-catchment" in body["relationship_caveat"]


def test_public_catchment_hierarchy_navigation(
    catchment_api: TestClient,
) -> None:
    rbd = catchment_api.get("/v1/catchments/river-basin-districts/4")
    assert rbd.status_code == 200
    assert rbd.json()["river_basin_district_id"] == "4"
    assert rbd.json()["name"] == "Synthetic RBD"

    management = catchment_api.get("/v1/catchments/management-catchments/3101")
    assert management.status_code == 200
    assert management.json()["river_basin_district_id"] == "4"

    operational = catchment_api.get("/v1/catchments/operational-catchments/3471")
    assert operational.status_code == 200
    assert operational.json()["management_catchment_id"] == "3101"
    assert operational.json()["river_basin_district_id"] == "4"

    water_body = catchment_api.get("/v1/catchments/water-bodies/GBTEST001")
    assert water_body.status_code == 200

    body = water_body.json()

    assert body["water_body_id"] == "GBTEST001"
    assert body["operational_catchment_id"] == "3471"
    assert body["management_catchment_id"] == "3101"
    assert body["river_basin_district_id"] == "4"
    assert body["water_body_type"] == "River"
    assert body["geometry_url"] == ("/v1/catchments/water-bodies/GBTEST001/geometry")


def test_public_water_body_pagination_is_snapshot_pinned(
    catchment_api: TestClient,
) -> None:
    first = catchment_api.get(
        "/v1/catchments/water-bodies",
        params={"limit": 1},
    )

    assert first.status_code == 200

    first_body = first.json()

    assert [item["water_body_id"] for item in first_body["items"]] == ["GBTEST001"]
    assert first_body["next_after_id"] == "GBTEST001"

    second = catchment_api.get(
        "/v1/catchments/water-bodies",
        params={
            "limit": 1,
            "after_id": first_body["next_after_id"],
            "snapshot_id": first_body["dataset"]["snapshot_id"],
        },
    )

    assert second.status_code == 200

    second_body = second.json()

    assert [item["water_body_id"] for item in second_body["items"]] == ["GBTEST002"]
    assert second_body["next_after_id"] is None
    assert second_body["dataset"]["snapshot_id"] == first_body["dataset"]["snapshot_id"]


def test_public_water_body_geometry_preserves_publisher_features(
    catchment_api: TestClient,
) -> None:
    response = catchment_api.get("/v1/catchments/water-bodies/GBTEST001/geometry")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    assert response.headers["cache-control"] == "no-store"

    body = response.json()

    assert body["type"] == "FeatureCollection"
    assert body["water_body_id"] == "GBTEST001"
    assert len(body["features"]) == 2

    assert [feature["properties"]["geometry_kind"] for feature in body["features"]] == [
        "Catchment",
        "RiverLine",
    ]

    assert [feature["geometry"]["type"] for feature in body["features"]] == [
        "Polygon",
        "LineString",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/v1/catchments/river-basin-districts/999",
        "/v1/catchments/management-catchments/999",
        "/v1/catchments/operational-catchments/999",
        "/v1/catchments/water-bodies/GBMISSING",
        "/v1/catchments/water-bodies/GBMISSING/geometry",
    ],
)
def test_public_missing_catchment_entities_return_404(
    catchment_api: TestClient,
    path: str,
) -> None:
    response = catchment_api.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Catchment entity not found"}
    assert response.headers["cache-control"] == "no-store"
