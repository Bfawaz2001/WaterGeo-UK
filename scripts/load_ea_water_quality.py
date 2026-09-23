"""Atomically load a verified local EA Water Quality evidence directory."""

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine
from watergeo.db.water_quality_ingestion import load_snapshot
from watergeo.ingestion.water_quality import WaterQualityError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    engine = create_database_engine(
        IngestionSettings(),
        statement_timeout_ms=120000,
    )

    try:
        print(load_snapshot(engine, args.directory))
    except WaterQualityError as error:
        print(f"Water quality load failed: {error}")
        return 1
    except (OSError, SQLAlchemyError) as error:
        print(f"Water quality load failed: {type(error).__name__}")
        return 1
    finally:
        engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
