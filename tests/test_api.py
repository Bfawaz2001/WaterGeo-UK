import json
import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings
from watergeo.core.logging import JsonFormatter
from watergeo.db.engine import SCHEMA_REVISION


@pytest.fixture
def database() -> MagicMock:
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = SCHEMA_REVISION
    return engine


@pytest.fixture
def client(database: MagicMock):
    settings = Settings(_env_file=None, db_password=SecretStr("test-password-long"))
    app = create_app(settings)
    app.dependency_overrides[get_database] = lambda: database
    with TestClient(app) as test_client:
        yield test_client


def test_health_does_not_need_database(client: TestClient, database: MagicMock) -> None:
    database.connect.side_effect = AssertionError("Liveness must not access the database")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    database.connect.assert_not_called()


def test_readiness_success(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize("error_class", [OperationalError, ProgrammingError])
def test_readiness_failure_is_sanitised(client, database, caplog, error_class) -> None:
    database.connect.side_effect = error_class("private query", {}, Exception("secret credential"))
    logger = logging.getLogger("watergeo.db.engine")
    logger.addHandler(caplog.handler)
    try:
        response = client.get("/ready")
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    output = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "secret credential" not in output + response.text
    assert "private query" not in output + response.text
    assert "database_unavailable" in output
    assert all(record.exc_info is None for record in caplog.records)


def test_readiness_rejects_wrong_schema_revision(client, database) -> None:
    connection = database.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = "unexpected"
    assert client.get("/ready").status_code == 503


def test_openapi_documents_public_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/health",
        "/ready",
        "/v1/sources/status",
        "/v1/water-quality/dataset",
        "/v1/water-quality/observations/{retrieval_id}",
        "/v1/water-quality/sampling-points",
        "/v1/water-quality/sampling-points/near",
        "/v1/water-quality/sampling-points/{sampling_point_id}",
        "/v1/water-supply/dataset",
        "/v1/hydrology/dataset",
        "/v1/hydrology/stations",
        "/v1/hydrology/stations/near",
        "/v1/hydrology/stations/{station_id}",
        "/v1/hydrology/history/{retrieval_id}",
        "/v1/catchments/dataset",
        "/v1/catchments/river-basin-districts",
        "/v1/catchments/river-basin-districts/{entity_id}",
        "/v1/catchments/management-catchments",
        "/v1/catchments/management-catchments/{entity_id}",
        "/v1/catchments/operational-catchments",
        "/v1/catchments/operational-catchments/{entity_id}",
        "/v1/catchments/water-bodies",
        "/v1/catchments/water-bodies/{entity_id}",
        "/v1/catchments/water-bodies/{entity_id}/geometry",
        "/v1/water-supply/areas",
        "/v1/water-supply/areas/at-point",
        "/v1/water-supply/areas/{source_id}",
        "/v1/water-supply/areas/{source_id}/geometry",
    }
    assert "503" in paths["/ready"]["get"]["responses"]


def test_cors_is_not_enabled(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_engine_is_disposed_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock(spec=Engine)
    monkeypatch.setattr("watergeo.api.app.create_database_engine", lambda _: engine)
    app = create_app(Settings(_env_file=None, db_password=SecretStr("test-password-long")))
    with TestClient(app):
        engine.dispose.assert_not_called()
    engine.dispose.assert_called_once()


def test_json_logs_exclude_arbitrary_extra_fields() -> None:
    record = logging.LogRecord(
        "watergeo.test", logging.WARNING, __file__, 1, "event_name", (), None
    )
    record.password = "secret credential"
    record.error_type = "OperationalError"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "event_name"
    assert payload["error_type"] == "OperationalError"
    assert "password" not in payload
    assert "timestamp" in payload
