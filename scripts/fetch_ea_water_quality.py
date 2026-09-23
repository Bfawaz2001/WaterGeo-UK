"""Retrieve EA Water Quality Explorer sampling-point evidence; no database access."""

from watergeo.ingestion.water_quality import WaterQualityError
from watergeo.ingestion.water_quality_client import fetch_snapshot, read_snapshot


def main() -> int:
    try:
        directory = fetch_snapshot()
        _, data = read_snapshot(directory)
    except WaterQualityError as error:
        print(f"Water quality retrieval failed: {error}")
        return 1
    except OSError as error:
        print(f"Water quality retrieval failed: {type(error).__name__}")
        return 1

    print(f"Evidence directory: {directory}")
    print(data.counts)
    print(f"Normalized SHA-256: {data.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
