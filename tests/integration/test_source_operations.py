"""Operational contracts against disposable PostGIS and synthetic evidence."""

import json
import subprocess
import sys
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_hydrology_http import bundle as bundle
from test_hydrology_http import engines as engines
from test_hydrology_http import loaded as loaded

from watergeo.api.app import create_app
from watergeo.core.config import Settings
from watergeo.db.source_status import source_statuses
from watergeo.operations.refresh import (
    RefreshBusy,
    RefreshRequest,
    assert_lock,
    refresh,
    source_lock,
)


def test_no_compatible_snapshots_are_unavailable(engines, monkeypatch):
    for name in (
        "OFWAT_WATER_SUPPLY_TRANSFORMATION",
        "HYDROLOGY_VERSION",
        "HISTORY_VERSION",
        "CATCHMENT_VERSION",
    ):
        monkeypatch.setattr("watergeo.db.source_status." + name, "synthetic-unavailable")
    result = source_statuses(engines[1], Settings())
    assert len(result.sources) == 4
    assert all(item.availability == "unavailable" for item in result.sources)
    assert all(item.snapshot_id is None for item in result.sources)


def test_status_with_accepted_dynamic_snapshot(engines, loaded):
    config = Settings(
        hydrology_retrieval_max_age_seconds=3600, hydrology_observation_max_age_seconds=3600
    )
    with TestClient(create_app(config)) as client:
        response = client.get("/v1/sources/status")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = {item["source"]: item for item in response.json()["sources"]}
        hydro = data["hydrology"]
        assert hydro["snapshot_id"] == str(loaded["snapshot_id"])
        assert hydro["availability"] == "available"
        assert hydro["retrieval_freshness"] == "current"
        assert hydro["observation_freshness"] == "stale"
        assert hydro["observation_count"] == 3
        assert hydro["missing_value_count"] == 1
        assert hydro["measures_without_observation_count"] == 0
        assert hydro["observation_oldest_at"].startswith("2020-")
        assert client.get("/ready").status_code == 200


def test_refresh_lock_contention_and_release(engines, bundle):
    request = RefreshRequest("hydrology", bundle)
    with source_lock(engines[0], "hydrology") as connection:
        assert_lock(connection, "hydrology")
        with pytest.raises(RefreshBusy):
            refresh(engines[0], request, "contender")
        with source_lock(engines[0], "catchments") as independent:
            assert_lock(independent, "catchments")
    with pytest.raises(ValueError), source_lock(engines[0], "hydrology"):
        raise ValueError("synthetic failure")
    with source_lock(engines[0], "hydrology") as connection:
        assert_lock(connection, "hydrology")
        connection.execute(text("SELECT pg_advisory_unlock_all()"))
        with pytest.raises(RuntimeError, match="lock lost"):
            assert_lock(connection, "hydrology")


def test_offline_cli_retry_and_concurrency(engines, bundle, loaded):
    command = [
        sys.executable,
        "scripts/refresh_sources.py",
        "hydrology",
        "--evidence-dir",
        str(bundle),
        "--timeout-seconds",
        "30",
    ]
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)  # noqa: S603
        assert result.returncode == 0, result.stdout
        events = [json.loads(line) for line in result.stdout.splitlines()]
        completed = next(item for item in events if item["event"] == "refresh_complete")
        assert completed["status"] == "existing"
        assert completed["snapshot_id"] == str(loaded["snapshot_id"])
        assert [item["phase"] for item in events if item["event"] == "refresh_phase"] == [
            "validate",
            "load",
        ]
        assert not result.stderr
    with source_lock(engines[0], "hydrology"):
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)  # noqa: S603
        assert result.returncode == 3
        assert "refresh_busy" in result.stdout


def test_latest_compatible_snapshot_and_uuid_tiebreak(engines, loaded):
    """Metadata copies intentionally isolate selection from normalizer behaviour."""
    identifiers = [UUID(int=100), UUID(int=101), UUID(int=102)]
    try:
        with engines[2].begin() as connection:
            for index, identifier in enumerate(identifiers):
                connection.execute(
                    text("""
                    INSERT INTO watergeo.hydrology_snapshot
                    SELECT :id, :hash, normalized_sha256,
                        CASE WHEN :index=2 THEN 'unsupported-version'
                            ELSE normalization_version END,
                        retrieval_started_at, retrieval_completed_at + interval '1 day', manifest,
                        station_count, station_with_location_count, station_without_location_count,
                        measure_count, latest_observation_count
                    FROM watergeo.hydrology_snapshot WHERE id=:original
                """),
                    {
                        "id": identifier,
                        "hash": str(index + 1) * 64,
                        "index": index,
                        "original": loaded["snapshot_id"],
                    },
                )
        data = source_statuses(engines[1], Settings())
        hydro = next(item for item in data.sources if item.source == "hydrology")
        assert hydro.snapshot_id == identifiers[1]
        assert hydro.snapshot_age_seconds is None
        assert hydro.retrieval_freshness == "unknown"
        assert hydro.observation_freshness == "unknown"
        assert hydro.measures_without_observation_count == 3
    finally:
        with engines[2].begin() as connection:
            for identifier in identifiers:
                connection.execute(
                    text("DELETE FROM watergeo.hydrology_snapshot WHERE id=:id"), {"id": identifier}
                )
