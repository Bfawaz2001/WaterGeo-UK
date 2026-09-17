"""Fetch the reviewed Ofwat water-supply boundary archive."""

from watergeo.ingestion.ofwat_boundaries import (
    OFWAT_WATER_SUPPLY_V1_5,
    BoundaryRetrievalError,
    fetch_boundary_source,
)


def main() -> int:
    try:
        result = fetch_boundary_source()
    except BoundaryRetrievalError as error:
        print(f"Ofwat boundary retrieval failed: {error}")
        return 1

    print(f"Dataset:  {OFWAT_WATER_SUPPLY_V1_5.dataset}")
    print(f"Release:  {OFWAT_WATER_SUPPLY_V1_5.release}")
    print("Status:   verified")
    print(f"Bytes:    {result.byte_count}")
    print(f"SHA-256:  {result.sha256}")
    print(f"Stored:   {result.archive_path}")
    print(f"Manifest: {result.manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
