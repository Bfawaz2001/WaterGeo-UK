"""Explicit opt-in: run only against a disposable, bootstrapped database."""

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from watergeo.api.app import create_app
from watergeo.core.config import Settings
from watergeo.db.engine import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("WATERGEO_TEST_DATABASE") != "1",
        reason="Set WATERGEO_TEST_DATABASE=1 with a disposable PostGIS database to opt in",
    ),
]


def test_migration_round_trip_and_readiness() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Re-running a deployment is safe.
    with TestClient(create_app()) as client:
        assert client.get("/ready").status_code == 200
        try:
            command.downgrade(config, "base")
            assert client.get("/ready").status_code == 503
            assert client.get("/health").status_code == 200
        finally:
            command.upgrade(config, "head")
        assert client.get("/ready").status_code == 200


def test_postgis_and_runtime_privileges() -> None:
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT ST_AsText(ST_SetSRID(ST_MakePoint(-1.89, 52.48), 4326))")
                ).scalar_one()
                == "POINT(-1.89 52.48)"
            )
            assert not connection.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
            assert not connection.execute(
                text("SELECT has_schema_privilege(current_user, 'watergeo', 'CREATE')")
            ).scalar_one()
        with engine.connect() as connection:
            # Turning off the convenience read-only flag must not bypass actual grants.
            connection.execute(text("SET TRANSACTION READ WRITE"))
            with pytest.raises(DBAPIError) as error:
                connection.execute(text("DELETE FROM watergeo.alembic_version"))
            assert error.value.orig.sqlstate == "42501"
    finally:
        engine.dispose()
