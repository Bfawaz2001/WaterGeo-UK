from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings
from watergeo.db.search import SearchQueries


def test_search_validation_is_bounded_and_forbids_unknown_parameters() -> None:
    engine = MagicMock(spec=Engine)
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: engine
    with TestClient(app) as client:
        assert client.get("/v1/search", params={"q": "a"}).status_code == 422
        assert client.get("/v1/search", params={"q": "ab", "limit": 31}).status_code == 422
        assert client.get("/v1/search", params={"q": "ab", "other": "x"}).status_code == 422
    engine.connect.assert_not_called()


def test_search_database_failure_is_generic_and_sanitised(capsys) -> None:
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = OperationalError(
        "private SQL", {}, Exception("private credential")
    )
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/v1/search", params={"q": "river"})
    assert response.status_code == 503
    assert response.json() == {"detail": "WaterGeo search unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text + capsys.readouterr().out


def test_search_treats_sql_wildcards_as_literal_text() -> None:
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
    matches = MagicMock()
    matches.mappings.return_value = []
    availability = MagicMock()
    availability.mappings.return_value.one.return_value = {
        "hydrology": False,
        "water_quality": False,
        "reservoirs": False,
        "thames_discharge": False,
        "water_body": False,
        "water_supply": False,
    }
    connection.execute.side_effect = [matches, availability]
    response = SearchQueries(engine).search(" %_ ", limit=12)
    assert response.items == []
    assert response.unavailable_kinds == [
        "hydrology",
        "water-quality",
        "reservoirs",
        "thames-discharge",
        "water-body",
        "water-supply",
    ]
    parameters = connection.execute.call_args_list[0].args[1]
    assert parameters["term"] == "%_"
    assert parameters["prefix"] == r"\%\_%"
