"""Exact-measure discovery and existing history HTTP contracts, with no publisher IO."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from watergeo.api.app import create_app, get_database
from watergeo.core.config import Settings
from watergeo.db.hydrology_history import InvalidHistoryCursor, list_history_retrievals

ID = UUID("11111111-1111-4111-8111-111111111111")
MEASURE = "exact-level-i-900-m-qualified"
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def metadata():
    return {
        "retrieval_id": ID,
        "measure_id": MEASURE,
        "requested_from": NOW,
        "requested_to": NOW,
        "retrieval_started_at": NOW,
        "retrieval_completed_at": NOW,
        "record_count": 0,
        "content_sha256": "a" * 64,
        "normalized_sha256": "b" * 64,
        "normalization_version": "ea-hydrology-history-v1",
    }


@pytest.fixture
def client():
    app = create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    app.dependency_overrides[get_database] = lambda: MagicMock(spec=Engine)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"measure_id": "bad/identifier"},
        {"measure_id": "x" * 257},
        {"measure_id": MEASURE, "limit": 0},
        {"measure_id": MEASURE, "limit": 101},
        {"measure_id": MEASURE, "after_id": "bad"},
        {"measure_id": MEASURE, "extra": "1"},
    ],
)
def test_invalid_discovery_queries(client, params):
    with patch("watergeo.api.hydrology_history.list_history_retrievals") as query:
        assert client.get("/v1/hydrology/history/retrievals", params=params).status_code == 422
        query.assert_not_called()


def test_discovery_route_precedes_uuid_route_and_preserves_provenance(client):
    with patch(
        "watergeo.api.hydrology_history.list_history_retrievals", return_value=([metadata()], ID)
    ) as query:
        response = client.get(
            "/v1/hydrology/history/retrievals", params={"measure_id": MEASURE, "limit": 1}
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["measure_id"] == MEASURE
    assert body["items"][0]["retrieval_id"] == str(ID)
    assert body["items"][0]["normalized_sha256"] == "b" * 64
    assert body["items"][0]["record_count"] == 0
    assert body["next_after_id"] == str(ID)
    assert "snapshot_id" not in body["items"][0]
    assert query.call_args.kwargs == {"limit": 1, "after_id": None}
    assert query.call_args.args[1] == MEASURE


def test_valid_empty_discovery(client):
    with patch("watergeo.api.hydrology_history.list_history_retrievals", return_value=([], None)):
        response = client.get("/v1/hydrology/history/retrievals", params={"measure_id": "unknown"})
    assert response.status_code == 200
    assert response.json() == {"measure_id": "unknown", "items": [], "next_after_id": None}


@pytest.mark.parametrize(
    "error,status",
    [
        (InvalidHistoryCursor(), 422),
        (OperationalError("select", {}, None), 503),
    ],
)
def test_discovery_errors(client, error, status):
    with patch("watergeo.api.hydrology_history.list_history_retrievals", side_effect=error):
        response = client.get(
            "/v1/hydrology/history/retrievals", params={"measure_id": MEASURE, "after_id": str(ID)}
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


def test_invalid_stored_output_is_503(client):
    with patch("watergeo.api.hydrology_history.list_history_retrievals", return_value=([{}], None)):
        assert (
            client.get(
                "/v1/hydrology/history/retrievals", params={"measure_id": MEASURE}
            ).status_code
            == 503
        )


def test_query_uses_exact_index_key_stable_order_and_bounded_lookahead():
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    second = {**metadata(), "retrieval_id": UUID("00000000-0000-4000-8000-000000000001")}
    connection.execute.return_value.mappings.return_value = [metadata(), second]
    rows, next_id = list_history_retrievals(engine, MEASURE, limit=1, after_id=None)
    assert rows == [metadata()]
    assert next_id == ID
    statement, params = connection.execute.call_args.args
    assert "WHERE measure_id = :measure_id" in str(statement)
    assert "ORDER BY retrieval_completed_at DESC, id DESC" in str(statement)
    assert "LIMIT :limit" in str(statement)
    assert params == {"measure_id": MEASURE, "limit": 2, "after_time": None, "after_id": None}


def test_cursor_belongs_to_exact_measure():
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(InvalidHistoryCursor):
        list_history_retrievals(engine, MEASURE, limit=1, after_id=ID)
    assert connection.execute.call_count == 1
    assert connection.execute.call_args.args[1] == {"id": ID, "measure_id": MEASURE}


def test_cursor_keyset_and_end_page():
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = NOW
    connection.execute.return_value.mappings.return_value = [metadata()]
    rows, next_id = list_history_retrievals(engine, MEASURE, limit=10, after_id=ID)
    assert rows == [metadata()] and next_id is None
    statement, params = connection.execute.call_args.args
    assert "(retrieval_completed_at, id) <" in str(statement)
    assert params["after_time"] == NOW and params["after_id"] == ID


def test_existing_history_404_422_and_503(client):
    path = f"/v1/hydrology/history/{ID}"
    with patch("watergeo.api.hydrology_history.get_history_retrieval", return_value=None):
        assert client.get(path).status_code == 404
    assert client.get(path, params={"after": "2026-10-01T00:00:00"}).status_code == 422
    assert client.get(path, params={"limit": 1001}).status_code == 422
    with patch(
        "watergeo.api.hydrology_history.get_history_retrieval",
        side_effect=OperationalError("select", {}, None),
    ):
        assert client.get(path).status_code == 503
