"""Load the reviewed Ofwat water-supply snapshot into canonical PostGIS."""

from sqlalchemy.exc import SQLAlchemyError

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine
from watergeo.ingestion.ofwat_canonical import (
    CanonicalIngestionError,
    load_reviewed_water_supply,
)


def main() -> int:
    try:
        settings = IngestionSettings()

        engine = create_database_engine(
            settings,
            statement_timeout_ms=60_000,
        )

        try:
            result = load_reviewed_water_supply(engine)
        finally:
            engine.dispose()

    except CanonicalIngestionError as error:
        print(f"Canonical Ofwat load failed: {error}")
        return 1

    except SQLAlchemyError as error:
        print(f"Canonical Ofwat load failed: {type(error).__name__}")
        return 1

    print("Dataset:       Ofwat water-supply areas")
    print("Release:       v1_5")
    print(f"Status:        {result.status}")
    print(f"Snapshot ID:   {result.snapshot_id}")
    print(f"Areas:         {result.area_count}")
    print(f"Transformed:   {result.transformed_count}")

    if result.status == "existing":
        print("Result:        verified no-op")
    else:
        print("Result:        atomic commit complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
