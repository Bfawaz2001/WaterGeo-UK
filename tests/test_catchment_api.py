"""HTTP validation, failure boundaries and public catchment API contracts."""

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

PREFIX = "/v1/catchments"


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
        "/dataset?unexpected=1",
        "/river-basin-districts?limit=0",
        "/river-basin-districts?limit=101",
        "/river-basin-districts?limit=1.0",
        "/river-basin-districts?after_id=bad%20id",
        "/river-basin-districts?unexpected=1",
        "/river-basin-districts/bad%20id",
        "/river-basin-districts/4?unexpected=1",
        "/management-catchments?limit=0",
        "/management-catchments?limit=101",
        "/management-catchments?after_id=bad%20id",
        "/management-catchments/bad%20id",
        "/operational-catchments?limit=0",
        "/operational-catchments?limit=101",
        "/operational-catchments?after_id=bad%20id",
        "/operational-catchments/bad%20id",
        "/water-bodies?limit=0",
        "/water-bodies?limit=101",
        "/water-bodies?after_id=bad%20id",
        "/water-bodies/bad%20id",
        "/water-bodies/bad%20id/geometry",
        "/water-bodies/GB104028047290?unexpected=1",
        "/water-bodies/GB104028047290/geometry?unexpected=1",
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
        "/river-basin-districts",
        "/river-basin-districts/4",
        "/management-catchments",
        "/management-catchments/3101",
        "/operational-catchments",
        "/operational-catchments/3471",
        "/water-bodies",
        "/water-bodies/GB104028047290",
        "/water-bodies/GB104028047290/geometry",
    ],
)
def test_database_failure_is_generic_and_sanitised(api, suffix, caplog):
    client, engine = api

    engine.connect.side_effect = OperationalError(
        "private SQL",
        {},
        Exception("secret credential"),
    )

    logger = logging.getLogger("watergeo.api.catchments")
    logger.addHandler(caplog.handler)

    try:
        response = client.get(PREFIX + suffix)
    finally:
        logger.removeHandler(caplog.handler)

    assert response.status_code == 503
    assert response.json() == {"detail": "Catchment dataset unavailable"}
    assert response.headers["cache-control"] == "no-store"

    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)

    assert "secret credential" not in logs + response.text
    assert "private SQL" not in logs + response.text
    assert all(record.exc_info is None for record in caplog.records)


def test_missing_snapshot_returns_503(api):
    client, engine = api

    result = engine.connect.return_value.__enter__.return_value
    mappings = result.execute.return_value.mappings.return_value
    mappings.first.return_value = None

    response = client.get(PREFIX + "/dataset")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catchment dataset unavailable"}


def test_openapi_contracts(api):
    client, _ = api

    spec = client.get("/openapi.json").json()

    geometry_responses = spec["paths"][PREFIX + "/water-bodies/{entity_id}/geometry"]["get"][
        "responses"
    ]

    assert "application/geo+json" in geometry_responses["200"]["content"]
    assert {"404", "413", "422", "503"} <= geometry_responses.keys()

    assert PREFIX + "/dataset" in spec["paths"]
    assert PREFIX + "/river-basin-districts" in spec["paths"]
    assert PREFIX + "/management-catchments" in spec["paths"]
    assert PREFIX + "/operational-catchments" in spec["paths"]
    assert PREFIX + "/water-bodies" in spec["paths"]
