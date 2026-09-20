"""Fetch a complete Environment Agency Catchment Data Explorer Cycle 3 snapshot."""

import argparse
from pathlib import Path

from watergeo.ingestion.catchment_client import CATCHMENT_ROOT, fetch_snapshot
from watergeo.ingestion.catchments import CatchmentError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=CATCHMENT_ROOT,
        help="Root directory for immutable raw catchment evidence",
    )
    args = parser.parse_args()

    try:
        directory = fetch_snapshot(args.output_root)
    except (CatchmentError, OSError) as error:
        print(f"Catchment fetch failed: {error}")
        return 1

    print(directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
