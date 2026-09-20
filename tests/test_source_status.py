from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.api.source_models import SourceStatuses
from watergeo.core.config import Settings
from watergeo.db.source_status import describe

NOW = datetime(2026, 9, 20, tzinfo=UTC)
SOURCES = ("ofwat", "hydrology", "hydrology-history", "catchments")


def settings(**kwargs):
    return Settings(_env_file=None, db_password=SecretStr("synthetic-password"), **kwargs)


@pytest.mark.parametrize("source", SOURCES)
def test_unavailable(source):
    result = describe(source, None, NOW, settings())
    assert result.availability == "unavailable"
    assert result.snapshot_id is None
    assert result.snapshot_age_seconds is None
    assert result.retrieval_freshness == "unknown"


@pytest.mark.parametrize("source", ("ofwat", "hydrology-history", "catchments"))
def test_versioned_and_bounded_sources_are_not_declared_stale(source):
    result = describe(source, {"retrieved_at": NOW - timedelta(days=1000)}, NOW, settings())
    assert result.availability == "available"
    assert result.snapshot_age_seconds == 86400000
    assert result.retrieval_freshness == result.observation_freshness == "not_applicable"


@pytest.mark.parametrize(
    "age,limit,expected",
    [(60, None, "unknown"), (60, 60, "current"), (61, 60, "stale"), (-1, 60, "unknown")],
)
def test_explicit_dynamic_age_policy(age, limit, expected):
    result = describe(
        "hydrology",
        {"retrieved_at": NOW - timedelta(seconds=age)},
        NOW,
        settings(hydrology_retrieval_max_age_seconds=limit),
    )
    assert result.retrieval_freshness == expected
    assert result.observation_freshness == "unknown"


@pytest.mark.parametrize(
    "oldest,newest,missing,absent,expected",
    [
        (30, 10, 0, 0, "current"),
        (61, 10, 0, 0, "stale"),
        (30, 10, 1, 0, "unknown"),
        (30, 10, 0, 1, "unknown"),
        (30, -10, 0, 0, "unknown"),
        (None, None, 0, 0, "unknown"),
        (61, 10, 1, 1, "stale"),
    ],
)
def test_observation_age_is_separate_and_conservative(oldest, newest, missing, absent, expected):
    row = {
        "retrieved_at": NOW,
        "observation_oldest_at": NOW - timedelta(seconds=oldest) if oldest is not None else None,
        "observation_newest_at": NOW - timedelta(seconds=newest) if newest is not None else None,
        "missing_value_count": missing,
        "measures_without_observation_count": absent,
    }
    result = describe(
        "hydrology",
        row,
        NOW,
        settings(hydrology_retrieval_max_age_seconds=60, hydrology_observation_max_age_seconds=60),
    )
    assert result.retrieval_freshness == "current"
    assert result.observation_freshness == expected


@pytest.mark.parametrize("limit", [0, -1, 31536001])
def test_invalid_policy_configuration(limit):
    with pytest.raises(ValidationError):
        settings(hydrology_retrieval_max_age_seconds=limit)


def test_empty_optional_age_limits_are_unconfigured():
    config = settings(
        hydrology_retrieval_max_age_seconds="", hydrology_observation_max_age_seconds=""
    )
    assert config.hydrology_retrieval_max_age_seconds is None
    assert config.hydrology_observation_max_age_seconds is None


def test_http_contract_query_and_database_failure(capsys):
    config = settings()
    app = create_app(config)
    app.dependency_overrides[get_database] = lambda: MagicMock(spec=Engine)
    unavailable = SourceStatuses(
        checked_at=NOW, sources=[describe(s, None, NOW, config) for s in SOURCES]
    )
    with (
        TestClient(app) as client,
        patch("watergeo.api.sources.source_statuses", return_value=unavailable) as read,
    ):
        response = client.get("/v1/sources/status")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert [item["source"] for item in response.json()["sources"]] == list(SOURCES)
        assert all(item["availability"] == "unavailable" for item in response.json()["sources"])
        read.reset_mock()
        assert client.get("/v1/sources/status?unexpected=1").status_code == 422
        read.assert_not_called()
        read.side_effect = OperationalError("private SQL", {}, Exception("secret password"))
        response = client.get("/v1/sources/status")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/health").status_code == 200
    output = capsys.readouterr().out + response.text
    assert "source_status_unavailable" in output
    assert "private SQL" not in output and "secret password" not in output
