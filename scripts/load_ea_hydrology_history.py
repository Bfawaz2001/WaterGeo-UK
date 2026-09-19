"""Atomically load a verified local EA historical evidence directory."""

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine
from watergeo.db.hydrology_history_ingestion import load_history
from watergeo.ingestion.hydrology import HydrologyError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    engine = create_database_engine(
        IngestionSettings(),
        statement_timeout_ms=60000,
    )

    try:
        print(load_history(engine, args.directory))
    except HydrologyError as error:
        print(f"Hydrology history load failed: {error}")
        return 1
    except (OSError, SQLAlchemyError) as error:
        print(f"Hydrology history load failed: {type(error).__name__}")
        return 1
    finally:
        engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
