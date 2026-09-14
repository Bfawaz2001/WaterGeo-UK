"""Use migration credentials independently from the read-only API credentials."""

from alembic import context

from watergeo.core.config import MigrationSettings
from watergeo.db.engine import create_database_engine

settings = MigrationSettings()

if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="watergeo",
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, version_table_schema="watergeo")
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
