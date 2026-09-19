"""Retrieve official EA river snapshots; no database access."""

from watergeo.ingestion.hydrology import HydrologyError
from watergeo.ingestion.hydrology_client import fetch_snapshot, read_snapshot


def main() -> int:
    try:
        directory = fetch_snapshot()
        _, data = read_snapshot(directory)
    except HydrologyError as error:
        print(f"Hydrology retrieval failed: {error}")
        return 1
    except OSError as error:
        print(f"Hydrology retrieval failed: {type(error).__name__}")
        return 1
    print(f"Evidence directory: {directory}")
    print(data.counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
