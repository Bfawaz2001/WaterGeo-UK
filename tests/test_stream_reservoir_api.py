from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings


@pytest.mark.parametrize(
    "path",
    [
        "dataset",
        "reservoirs",
        "reservoirs/10014",
        "reservoirs/near?lon=0&lat=0",
        "reservoirs/10014/readings",
    ],
)
def test_stream_reservoir_database_failure_is_sanitized(path, capsys):
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = OperationalError(
        "private SQL", {}, Exception("private credential")
    )
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/v1/severn-trent/reservoir-levels/" + path)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text + capsys.readouterr().out
