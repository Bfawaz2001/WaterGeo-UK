"""Retrieve one bounded official EA historical measure window; no database access."""

import argparse
from datetime import datetime

from watergeo.ingestion.hydrology import HydrologyError
from watergeo.ingestion.hydrology_history_client import (
    fetch_history,
    read_history,
)


def aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected ISO 8601 date-time") from error

    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Date-time must include a timezone")

    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("measure_id")
    parser.add_argument("--from", dest="requested_from", required=True, type=aware_datetime)
    parser.add_argument("--to", dest="requested_to", required=True, type=aware_datetime)

    args = parser.parse_args()

    try:
        directory = fetch_history(
            args.measure_id,
            args.requested_from,
            args.requested_to,
        )
        manifest, data = read_history(directory)
    except HydrologyError as error:
        print(f"Hydrology history retrieval failed: {error}")
        return 1
    except OSError as error:
        print(f"Hydrology history retrieval failed: {type(error).__name__}")
        return 1

    print(f"Evidence directory: {directory}")
    print(
        {
            "measure_id": data.measure_id,
            "record_count": data.record_count,
            "requested_from": manifest["requested_from"],
            "requested_to": manifest["requested_to"],
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
