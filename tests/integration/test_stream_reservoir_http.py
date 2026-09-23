"""Synthetic Stream reservoir publication, HTTP and least-privilege contracts."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from test_hydrology_http import engines as engines

from watergeo.api.app import create_app
from watergeo.db.stream_reservoir_ingestion import load_snapshot
from watergeo.ingestion import stream_reservoir_client as source
from watergeo.ingestion.stream_reservoirs import (
    ITEM_ID,
    ITEM_TITLE,
    LAYER_NAME,
    SERVICE_ROOT,
    StreamReservoirError,
)
from watergeo.operations.refresh import RefreshRequest, refresh


def transport() -> httpx.MockTransport:
    field_types = {
        "RESERVOIR_ID": "esriFieldTypeString",
        "RESERVOIR_NAME": "esriFieldTypeString",
        "DATE": "esriFieldTypeDate",
        "LATITUDE": "esriFieldTypeString",
        "LONGITUDE": "esriFieldTypeString",
        "CAPACITY": "esriFieldTypeString",
        "CAPACITY_UNITS": "esriFieldTypeString",
        "CURRENT_LEVEL": "esriFieldTypeString",
        "CURRENT_LEVEL_UNITS": "esriFieldTypeString",
        "CURRENT_PERCENTAGE": "esriFieldTypeDouble",
        "FID": "esriFieldTypeOID",
    }

    def feature(identity: int, reservoir: str, observed: int, percentage: float):
        return {
            "type": "Feature",
            "properties": {
                "RESERVOIR_ID": reservoir,
                "RESERVOIR_NAME": "DRAYCOTE RES" if reservoir == "10014" else "OTHER RES",
                "DATE": observed,
                "LATITUDE": "52.31929693",
                "LONGITUDE": "-1.318895597",
                "CAPACITY": "23000",
                "CAPACITY_UNITS": "ML",
                "CURRENT_LEVEL": "20746",
                "CURRENT_LEVEL_UNITS": "ML",
                "CURRENT_PERCENTAGE": percentage,
                "FID": identity,
            },
            "geometry": {"type": "Point", "coordinates": [-1.318895597, 52.31929693]},
        }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(ITEM_ID):
            body = {
                "id": ITEM_ID,
                "title": ITEM_TITLE,
                "type": "Feature Service",
                "access": "public",
                "accessInformation": "Severn Trent Water",
                "url": SERVICE_ROOT,
                "created": 1779029424000,
                "modified": 1779030284000,
                "licenseInfo": "Licensed under CC BY 4.0",
            }
        elif request.url.path.endswith("/FeatureServer/0"):
            body = {
                "id": 0,
                "name": LAYER_NAME,
                "type": "Feature Layer",
                "geometryType": "esriGeometryPoint",
                "objectIdField": "FID",
                "capabilities": "Query",
                "maxRecordCount": 2000,
                "extent": {"spatialReference": {"wkid": 102100, "latestWkid": 3857}},
                "dateFieldsTimeReference": {
                    "timeZone": "UTC",
                    "timeZoneIANA": "Etc/UTC",
                    "respectsDaylightSaving": False,
                },
                "fields": [
                    {"name": name, "type": field_type} for name, field_type in field_types.items()
                ],
            }
        elif request.url.params.get("returnIdsOnly") == "true":
            body = {"objectIdFieldName": "FID", "objectIds": [1, 2]}
        else:
            body = {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                "features": [
                    feature(1, "10014", 1736121600000, 90.2),
                    feature(2, "10015", 1736726400000, 80.0),
                ],
            }
        return httpx.Response(
            200,
            json=body,
            headers={"content-type": "application/json"},
            request=request,
        )

    return httpx.MockTransport(respond)


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source.time, "sleep", lambda _: None)


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    return source.fetch_snapshot(tmp_path, transport=transport())


@pytest.fixture
def loaded(engines, bundle: Path) -> Iterator[dict[str, Any]]:
    result = load_snapshot(engines[0], bundle)
    yield result
    with engines[2].begin() as connection:
        connection.execute(
            text("DELETE FROM watergeo.stream_reservoir_level WHERE snapshot_id=:id"),
            {"id": result["snapshot_id"]},
        )
        connection.execute(
            text("DELETE FROM watergeo.stream_reservoir WHERE snapshot_id=:id"),
            {"id": result["snapshot_id"]},
        )
        connection.execute(
            text("DELETE FROM watergeo.stream_reservoir_snapshot WHERE id=:id"),
            {"id": result["snapshot_id"]},
        )


def test_atomic_retry_geometry_and_stored_content(engines, bundle: Path, loaded: dict[str, Any]):
    assert loaded["status"] == "inserted"
    assert load_snapshot(engines[0], bundle) == {**loaded, "status": "existing"}
    with engines[1].connect() as connection:
        rows = connection.execute(
            text("""
                SELECT reservoir_id,public.ST_SRID(geom),public.ST_AsText(geom)
                FROM watergeo.stream_reservoir WHERE snapshot_id=:id
                ORDER BY reservoir_id COLLATE "C"
            """),
            {"id": loaded["snapshot_id"]},
        ).all()
    assert rows == [
        ("10014", 4326, "POINT(-1.318895597 52.31929693)"),
        ("10015", 4326, "POINT(-1.318895597 52.31929693)"),
    ]


def test_http_dataset_list_detail_near_and_readings(loaded: dict[str, Any]):
    prefix = "/v1/severn-trent/reservoir-levels"
    with TestClient(create_app()) as api:
        dataset = api.get(prefix + "/dataset")
        assert dataset.status_code == 200 and dataset.headers["cache-control"] == "no-store"
        metadata = dataset.json()
        assert metadata["reservoir_count"] == metadata["reading_count"] == 2
        assert metadata["licence"] == "Creative Commons Attribution 4.0"
        params = {"snapshot_id": metadata["snapshot_id"]}
        first = api.get(prefix + "/reservoirs", params={**params, "limit": 1}).json()
        assert [row["reservoir_id"] for row in first["items"]] == ["10014"]
        second = api.get(
            prefix + "/reservoirs", params={**params, "after_id": first["next_after_id"]}
        ).json()
        assert [row["reservoir_id"] for row in second["items"]] == ["10015"]
        detail = api.get(prefix + "/reservoirs/10014", params=params)
        assert detail.status_code == 200
        assert detail.json()["latest_reading"]["current_percentage"] == 90.2
        near = api.get(
            prefix + "/reservoirs/near",
            params={**params, "lon": -1.318895597, "lat": 52.31929693, "radius_m": 1},
        ).json()
        assert [(row["reservoir_id"], row["distance_m"]) for row in near["items"]] == [
            ("10014", 0),
            ("10015", 0),
        ]
        readings = api.get(prefix + "/reservoirs/10014/readings", params=params).json()
        assert len(readings["items"]) == 1
        assert readings["items"][0]["observed_at"] == "2025-01-06T00:00:00Z"
        assert "local date" in readings["timestamp_note"]
        assert api.get(prefix + "/reservoirs/missing", params=params).status_code == 404
        assert api.get(prefix + "/dataset?unexpected=1").status_code == 422
        assert api.get(prefix + "/reservoirs?limit=101").status_code == 422
        assert api.get(prefix + "/reservoirs/10014/readings?after=2025-01-01").status_code == 422


def test_refresh_retry_and_static_source_status(engines, bundle: Path, loaded: dict[str, Any]):
    result = refresh(engines[0], RefreshRequest("stream-reservoir-levels", bundle), "synthetic-run")
    assert result == {"status": "existing", "snapshot_id": loaded["snapshot_id"]}
    with TestClient(create_app()) as api:
        response = api.get("/v1/sources/status")
        assert response.status_code == 200
        status = next(
            row for row in response.json()["sources"] if row["source"] == "stream-reservoir-levels"
        )
        assert status["snapshot_id"] == loaded["snapshot_id"]
        assert status["source_version"] == "2025"
        assert status["retrieval_freshness"] == "not_applicable"
        assert status["observation_count"] == 2


def test_exact_retry_detects_stored_child_corruption(engines, bundle: Path, loaded: dict[str, Any]):
    with engines[2].begin() as connection:
        connection.execute(
            text("""
                UPDATE watergeo.stream_reservoir_level SET current_percentage=1
                WHERE snapshot_id=:id AND publisher_object_id=1
            """),
            {"id": loaded["snapshot_id"]},
        )
    with pytest.raises(StreamReservoirError, match="mismatch"):
        load_snapshot(engines[0], bundle)


def test_failed_child_insert_rolls_back(engines, bundle: Path):
    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO watergeo.stream_reservoir_level" in statement:
            raise RuntimeError("synthetic failure")

    event.listen(engines[0], "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic"):
            load_snapshot(engines[0], bundle)
    finally:
        event.remove(engines[0], "before_cursor_execute", fail)
    manifest, _ = source.read_snapshot(bundle)
    with engines[1].connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM watergeo.stream_reservoir_snapshot WHERE content_sha256=:h"),
            {"h": manifest["content_sha256"]},
        ).scalar_one()
    assert count == 0


def test_roles_and_constraints_remain_least_privilege(engines, loaded: dict[str, Any]):
    with engines[1].connect() as connection:
        for table in (
            "stream_reservoir_snapshot",
            "stream_reservoir",
            "stream_reservoir_level",
        ):
            for role in ("watergeo_app", "watergeo_ingest"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    actual = connection.execute(
                        text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {"role": role, "table": "watergeo." + table, "privilege": privilege},
                    ).scalar_one()
                    assert actual == (
                        privilege == "SELECT"
                        or (role == "watergeo_ingest" and privilege == "INSERT")
                    )
    with pytest.raises(DBAPIError), engines[0].begin() as connection:
        connection.execute(
            text("""
                INSERT INTO watergeo.stream_reservoir
                    (snapshot_id,reservoir_id,name,latitude,longitude,geom,capacity,capacity_unit)
                VALUES (:id,'invalid','bad',91,0,
                    public.ST_SetSRID(public.ST_MakePoint(0,91),4326),1,'ML')
            """),
            {"id": loaded["snapshot_id"]},
        )
