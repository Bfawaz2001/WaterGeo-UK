"""Bounded database connections and readiness checks."""

import logging

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from watergeo.core.config import DatabaseSettings

logger = logging.getLogger(__name__)
SCHEMA_REVISION = "0002"


def create_database_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=3000 -c lock_timeout=3000",
            "application_name": "watergeo",
        },
    )


def database_is_ready(engine: Engine) -> bool:
    """Require PostGIS and the schema version this application understands."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT public.PostGIS_Version()")).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM watergeo.alembic_version")
            ).scalar_one()
    except SQLAlchemyError as exc:
        # Driver messages can contain hosts, users, queries, or credentials.
        logger.warning("database_unavailable", extra={"error_type": type(exc).__name__})
        return False
    if revision != SCHEMA_REVISION:
        logger.warning("database_revision_mismatch")
        return False
    return True
