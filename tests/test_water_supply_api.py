"""HTTP validation, failure boundaries and public OpenAPI contracts without a DB."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings
from watergeo.core.logging import JsonFormatter

PREFIX = "/v1/water-supply"


@pytest.fixture
def api():
    engine = MagicMock(spec=Engine)
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: engine
    with TestClient(app) as client:
        yield client, engine


@pytest.mark.parametrize(
    "suffix",
    [
        "/areas/0",
        "/areas/-1",
        "/areas/1.0",
        "/areas/1e2",
        "/areas/true",
        "/areas/9223372036854775808",
        "/areas/1%20OR%201=1",
        "/areas/0/geometry",
        "/areas?limit=0",
        "/areas?limit=101",
        "/areas?limit=1.0",
        "/areas?after_id=-1",
        "/areas?after_id=9223372036854775808",
        "/areas?include_geometry=true",
        "/areas?bbox=-3,51,-2,52",
        "/areas?bbox=broken",
        "/dataset?unexpected=1",
        "/areas/1?unexpected=1",
        "/areas/1/geometry?unexpected=1",
        "/areas/at-point?lon=181&lat=52",
        "/areas/at-point?lon=-181&lat=52",
        "/areas/at-point?lon=-2&lat=91",
        "/areas/at-point?lon=-2&lat=-91",
        "/areas/at-point?lon=nan&lat=52",
        "/areas/at-point?lon=-2&lat=inf",
        "/areas/at-point?lon=-2",
        "/areas/at-point?lat=52",
        "/areas/at-point",
    ],
)
def test_invalid_parameters_do_not_access_database(api, suffix):
    client, engine = api
    response = client.get(PREFIX + suffix)
    assert response.status_code == 422
    engine.connect.assert_not_called()


@pytest.mark.parametrize(
    "suffix",
    [
        "/dataset",
        "/areas",
        "/areas/1",
        "/areas/1/geometry",
        "/areas/at-point?lon=-2&lat=52",
    ],
)
def test_database_failure_is_generic_and_sanitised(api, suffix, caplog):
    client, engine = api
    engine.connect.side_effect = OperationalError("private SQL", {}, Exception("secret credential"))
    logger = logging.getLogger("watergeo.api.water_supply")
    logger.addHandler(caplog.handler)
    try:
        response = client.get(PREFIX + suffix)
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 503
    assert response.json() == {"detail": "Water-supply dataset unavailable"}
    assert response.headers["cache-control"] == "no-store"
    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "secret credential" not in logs + response.text
    assert "private SQL" not in logs + response.text
    assert all(record.exc_info is None for record in caplog.records)


def test_missing_published_snapshot_returns_503(api):
    client, engine = api
    result = engine.connect.return_value.execute.return_value.mappings.return_value
    result.one_or_none.return_value = None
    assert client.get(PREFIX + "/dataset").status_code == 503
    engine.connect.return_value.close.assert_called_once()


def test_openapi_geojson_and_validation_contracts(api):
    client, _ = api
    spec = client.get("/openapi.json").json()
    responses = spec["paths"][PREFIX + "/areas/{source_id}/geometry"]["get"]["responses"]
    assert "application/geo+json" in responses["200"]["content"]
    assert {"404", "413", "422", "503"} <= responses.keys()
    assert (
        spec["components"]["schemas"]["MultiPolygon"]["properties"]["type"]["const"]
        == "MultiPolygon"
    )
