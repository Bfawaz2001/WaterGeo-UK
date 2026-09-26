from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings


def test_thames_database_failure_is_sanitized(capsys) -> None:
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = OperationalError(
        "private SQL", {}, Exception("private credential")
    )
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/v1/thames-water/discharge-status/dataset")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text + capsys.readouterr().out
