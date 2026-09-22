"""Operational contracts against disposable PostGIS and synthetic evidence."""

import json
import subprocess
import sys
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
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


@pytest.mark.parametrize("body_fails", [False, True])
def test_explicit_unlock_and_no_locked_session_returned_to_pool(engines, body_fails):
    unlocked = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        if "SELECT pg_advisory_unlock(" in statement:
            # Runs after PostgreSQL executes unlock, before connection invalidation.
            unlocked.append(
                connection.execute(
                    text("""
                SELECT count(*) FROM pg_locks
                WHERE pid=pg_backend_pid() AND locktype='advisory'
            """)
                ).scalar_one()
            )

    engine = engines[0]
    event.listen(engine, "after_cursor_execute", observe)
    try:
        try:
            with source_lock(engine, "hydrology") as connection:
                old_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
                assert_lock(connection, "hydrology")
                if body_fails:
                    raise ValueError("synthetic body failure")
        except ValueError:
            assert body_fails
        assert unlocked == [0]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() != old_pid
            assert (
                connection.execute(
                    text("""
                SELECT count(*) FROM pg_locks
                WHERE pid=pg_backend_pid() AND locktype='advisory'
            """)
                ).scalar_one()
                == 0
            )
        with source_lock(engine, "hydrology") as connection:
            assert_lock(connection, "hydrology")
    finally:
        event.remove(engine, "after_cursor_execute", observe)


def test_no_compatible_snapshots_are_unavailable(engines, monkeypatch):
    for name in (
        "OFWAT_WATER_SUPPLY_TRANSFORMATION",
        "HYDROLOGY_VERSION",
        "HISTORY_VERSION",
        "CATCHMENT_VERSION",
        "WATER_QUALITY_VERSION",
    ):
        monkeypatch.setattr("watergeo.db.source_status." + name, "synthetic-unavailable")
    result = source_statuses(engines[1], Settings())
    assert len(result.sources) == 5
    assert all(item.availability == "unavailable" for item in result.sources)
    assert all(item.snapshot_id is None for item in result.sources)


@pytest.mark.parametrize("body_fails", [False, True])
def test_failed_unlock_and_invalidation_still_dispose_locked_session(
    engines, monkeypatch, body_fails
):
    engine = engines[0]
    original = ValueError("body failure")
    cleanup = RuntimeError("invalidation failure")

    def fail_unlock(connection, cursor, statement, parameters, context, executemany):
        if "SELECT pg_advisory_unlock(" in statement:
            raise RuntimeError("unlock failure")

    def fail_invalidation():
        raise cleanup

    event.listen(engine, "before_cursor_execute", fail_unlock)
    try:
        with pytest.raises(Exception) as caught, source_lock(engine, "hydrology") as connection:
            driver = connection.connection.driver_connection
            assert_lock(connection, "hydrology")
            monkeypatch.setattr(connection, "invalidate", fail_invalidation)
            if body_fails:
                raise original
        assert caught.value is (original if body_fails else cleanup)
        assert driver.closed
    finally:
        event.remove(engine, "before_cursor_execute", fail_unlock)
    with source_lock(engine, "hydrology") as connection:
        assert_lock(connection, "hydrology")


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
    with (
        pytest.raises(RuntimeError, match="release not confirmed"),
        source_lock(engines[0], "hydrology") as connection,
    ):
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
