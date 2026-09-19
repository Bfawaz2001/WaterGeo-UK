"""HTTP-to-PostGIS tests with invented BNG shapes and runtime-role reads."""

import json
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from shapely.geometry import shape
from sqlalchemy import event, text

from watergeo.api.app import create_app, get_database
from watergeo.core.config import MigrationSettings, Settings
from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION
from watergeo.db.engine import create_database_engine
from watergeo.db.water_supply import POINT_PREDICATE

PREFIX = "/v1/water-supply"


@pytest.fixture(scope="module")
def api():
    command.upgrade(Config("alembic.ini"), "head")
    writer = create_database_engine(MigrationSettings())
    runtime = create_database_engine(Settings())
    snapshot_id, unrelated_id = uuid4(), uuid4()
    try:
        with writer.begin() as connection:
            for identifier, digest, version in (
                (snapshot_id, OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION),
                (unrelated_id, "d" * 64, "unpublished-newer-release"),
            ):
                connection.execute(
                    text("""
                    INSERT INTO watergeo.water_supply_snapshot
                    (id, source_sha256, source_url, source_bytes, retrieved_at, publisher,
                     distributor, licence_name, licence_url, attribution, transformation_version)
                    VALUES (:id, :digest, 'https://example.invalid/synthetic.zip', 123,
                            '2026-09-18T00:00:00Z', 'Synthetic publisher', 'Synthetic distributor',
                            'Open Government Licence', 'https://example.invalid/licence',
                            'Synthetic fixture, not Ofwat data', :version)
                """),
                    {"id": identifier, "digest": digest, "version": version},
                )
            for source_id in (1, 2, 3, 4):
                connection.execute(
                    text("""
                    WITH origin AS (
                        SELECT ST_Transform(ST_SetSRID(ST_Point(-2, 52), 4326), 27700) p
                    ), xy AS (SELECT ST_X(p) x, ST_Y(p) y FROM origin)
                    INSERT INTO watergeo.water_supply_area
                        (snapshot_id, source_id, source_fields, geom)
                    SELECT :snapshot, :id, CAST(:fields AS jsonb), ST_Multi(CASE :id
                        WHEN 1 THEN ST_MakeEnvelope(x-1000, y-1000, x, y+1000, 27700)
                        WHEN 2 THEN ST_MakeEnvelope(x, y-1000, x+1000, y+1000, 27700)
                        WHEN 3 THEN ST_MakeEnvelope(x-500, y-500, x+500, y+500, 27700)
                        ELSE ST_Difference(
                            ST_MakeEnvelope(x-2000, y-2000, x+2000, y+2000, 27700),
                            ST_MakeEnvelope(x-100, y-100, x+100, y+100, 27700))
                    END) FROM xy
                """),
                    {
                        "snapshot": snapshot_id,
                        "id": source_id,
                        "fields": json.dumps(
                            {
                                "ID": source_id,
                                "COMPANY": "Synthetic Dŵr Company",
                                "Acronym": "SYN",
                                "CoType": "Synthetic company type",
                                "AreaServed": f"Synthetic area {source_id}",
                                "AreaType": "Source label retained",
                                "Version": "1_5",
                                "LastUpdate": "2024-04-25",
                                "Date Grant": None,
                                "WARNINGS": "Synthetic warning",
                                "Licence": "Synthetic notice",
                                "Provenance": "Synthetic origin",
                                "Disclaimer": "Synthetic disclaimer",
                                "Disclaim2": "Synthetic premises exceptions",
                                "Disclaim3": "Synthetic coastline exceptions",
                                "unknown_internal": "omit",
                            }
                        ),
                    },
                )
            connection.execute(
                text("""
                INSERT INTO watergeo.water_supply_area_transformation
                (snapshot_id, source_id, transformation_id, method, keep_collapsed,
                 shapely_version, geos_version, invalid_reason, source_decoded_wkb_sha256,
                 canonical_wkb_sha256, review_status, review_reason, review_reference, details)
                VALUES (:id, 3, 'synthetic-review', 'structure', false, 'synthetic', 'synthetic',
                        'Synthetic invalidity', :source_hash, :canonical_hash, 'approved',
                        'Synthetic review reason', 'synthetic-test-reference',
                        '{"internal":"omit"}')
            """),
                {"id": snapshot_id, "source_hash": "a" * 64, "canonical_hash": "b" * 64},
            )
        app = create_app()
        app.dependency_overrides[get_database] = lambda: runtime
        with TestClient(app) as client:
            yield client, runtime, snapshot_id
    finally:
        # Delete only this module's synthetic rows; never run on the user's data DB.
        with writer.begin() as connection:
            connection.execute(
                text("""
                DELETE FROM watergeo.water_supply_area_transformation WHERE snapshot_id = :id
            """),
                {"id": snapshot_id},
            )
            connection.execute(
                text("DELETE FROM watergeo.water_supply_area WHERE snapshot_id = :id"),
                {"id": snapshot_id},
            )
            connection.execute(
                text("DELETE FROM watergeo.water_supply_snapshot WHERE id IN (:a, :b)"),
                {"a": snapshot_id, "b": unrelated_id},
            )
        writer.dispose()
        runtime.dispose()


def test_dataset_provenance_and_explicit_snapshot_selection(api):
    client, _, snapshot = api
    response = client.get(PREFIX + "/dataset")
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_id"] == str(snapshot)
    assert data["source_sha256"] == OFWAT_WATER_SUPPLY_SHA256
    assert data["licence_version"] is None
    assert data["area_count"] == 4
    assert data["transformed_area_count"] == 1
    assert data["stored_crs"] == "EPSG:27700"
    assert "legal record" in data["disclaimer"]


def test_listing_paginates_without_geometry_or_private_source_fields(api):
    client, _, snapshot = api
    first = client.get(PREFIX + "/areas?limit=2").json()
    assert first["snapshot_id"] == str(snapshot)
    assert [item["source_id"] for item in first["items"]] == [1, 2]
    assert first["next_after_id"] == 2
    second = client.get(PREFIX + "/areas?limit=2&after_id=2").json()
    assert [item["source_id"] for item in second["items"]] == [3, 4]
    assert second["next_after_id"] is None
    assert second["items"][0]["transformed"]
    assert first["items"][0]["company"] == "Synthetic Dŵr Company"
    assert first["items"][0]["source_last_update"] == "2024-04-25"
    assert "geometry" not in first["items"][0]
    assert "unknown_internal" not in json.dumps(first)
    assert client.get(PREFIX + "/areas?after_id=99").json()["items"] == []


def test_detail_preserves_notices_and_review_provenance(api):
    client, _, _ = api
    data = client.get(PREFIX + "/areas/3").json()
    assert data["licence_statement"] == "Synthetic notice"
    assert data["source_provenance"] == "Synthetic origin"
    assert data["premises_disclaimer"] == "Synthetic premises exceptions"
    assert data["coastline_disclaimer"] == "Synthetic coastline exceptions"
    assert data["transformation"]["method"] == "structure"
    assert data["transformation"]["keep_collapsed"] is False
    assert data["transformation"]["canonical_wkb_sha256"] == "b" * 64
    assert "details" not in data["transformation"]
    assert client.get(PREFIX + "/areas/1").json()["transformation"] is None
    assert client.get(PREFIX + "/areas/99").status_code == 404
    assert client.get(PREFIX + "/areas/99/geometry").status_code == 404


def test_geojson_is_valid_wgs84_and_does_not_mutate_canonical_geometry(api, monkeypatch):
    from watergeo.db.presentation_assessment import inspect_candidate

    client, runtime, snapshot = api
    # This invented ID 4 needs its own test contract; production ID 4 is reviewed.
    with runtime.connect() as connection:
        candidate = inspect_candidate(connection, snapshot, 4, "structure_drop")
    monkeypatch.setattr(
        "watergeo.db.water_supply.REVIEWED_WGS84_GEOMETRIES",
        {4: (candidate["canonical"]["wkb_sha256"], candidate["output"]["geojson_sha256"])},
    )
    query = text("""
        SELECT ST_AsEWKB(geom) wkb, ST_SRID(geom) srid,
               ST_Area(geom) area FROM watergeo.water_supply_area
        WHERE snapshot_id = :id AND source_id = 4
    """)
    with runtime.connect() as connection:
        before = connection.execute(query, {"id": snapshot}).one()
    response = client.get(PREFIX + "/areas/4/geometry")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geo+json"
    data = response.json()
    assert data["type"] == "Feature" and data["id"] == 4
    assert "crs" not in data["geometry"]
    geom = shape(data["geometry"])
    assert geom.is_valid and geom.geom_type == "MultiPolygon"
    assert -2.1 < geom.bounds[0] < -2 and 51.9 < geom.bounds[1] < 52
    assert len(geom.geoms[0].interiors) == 1
    assert geom.geoms[0].exterior.is_ccw
    assert not geom.geoms[0].interiors[0].is_ccw
    with runtime.connect() as connection:
        after = connection.execute(query, {"id": snapshot}).one()
    assert before == after and after.srid == 27700


def test_point_on_shared_boundary_returns_multiple_matches_and_respects_hole(api):
    client, _, _ = api
    data = client.get(PREFIX + "/areas/at-point?lon=-2&lat=52").json()
    assert [item["source_id"] for item in data["items"]] == [1, 2, 3]
    first = client.get(PREFIX + "/areas/at-point?lon=-2&lat=52&limit=1").json()
    assert first["next_after_id"] == 1
    rest = client.get(PREFIX + "/areas/at-point?lon=-2&lat=52&after_id=1").json()
    assert [item["source_id"] for item in rest["items"]] == [2, 3]


@pytest.mark.parametrize(
    ("lon", "lat", "ids"),
    [
        (-2.01, 52, [1, 4]),
        (-1, 53, []),
        (0, 0, []),
        (180, 90, []),
        (-180, -90, []),
    ],
)
def test_point_inside_and_outside(api, lon, lat, ids):
    client, _, _ = api
    response = client.get(PREFIX + "/areas/at-point", params={"lon": lon, "lat": lat})
    assert response.status_code == 200
    assert [item["source_id"] for item in response.json()["items"]] == ids


def test_geometry_size_limit_is_explicit(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr("watergeo.db.water_supply.MAX_GEOMETRY_BYTES", 10)
    response = client.get(PREFIX + "/areas/1/geometry")
    assert response.status_code == 413


def test_invalid_projected_representation_is_not_returned(api, monkeypatch):
    client, _, _ = api
    # Inject a geometry-stage result to exercise the real HTTP rejection path.
    # Valid canonical input can become invalid after nonlinear reprojection.
    monkeypatch.setattr(
        "watergeo.db.water_supply.GEOMETRY_SQL",
        text("""
        SELECT 100 AS byte_count, false AS valid,
               '{"type":"MultiPolygon","coordinates":[]}' AS geojson
    """),
    )
    response = client.get(PREFIX + "/areas/1/geometry")
    assert response.status_code == 503
    assert response.json() == {"detail": "Water-supply dataset unavailable"}


def test_list_query_count_does_not_grow_with_page_size(api):
    client, runtime, _ = api
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(runtime, "before_cursor_execute", capture)
    try:
        assert client.get(PREFIX + "/areas?limit=100").status_code == 200
    finally:
        event.remove(runtime, "before_cursor_execute", capture)
    assert len(statements) == 2
    assert all("ST_AsGeoJSON" not in statement for statement in statements)


def test_point_query_has_a_usable_spatial_index(api):
    _, runtime, _ = api
    with runtime.connect() as connection:
        # Check the production spatial predicate in isolation. On four rows the
        # full query can prefer its snapshot primary key to satisfy ORDER BY.
        # Real-data EXPLAIN is recorded separately in the PR verification.
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = connection.execute(
            text(
                "EXPLAIN (FORMAT JSON) SELECT a.source_id "
                "FROM watergeo.water_supply_area a WHERE true " + POINT_PREDICATE
            ),
            {
                "lon": -2,
                "lat": 52,
            },
        ).scalar_one()
    assert "water_supply_area_geom_idx" in json.dumps(plan)
