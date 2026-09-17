"""Validate the reviewed Ofwat water-supply boundary snapshot."""

from watergeo.ingestion.ofwat_boundary_validation import (
    BoundaryValidationError,
    validate_reviewed_water_supply,
)


def main() -> int:
    try:
        report, report_path = validate_reviewed_water_supply()
    except BoundaryValidationError as error:
        print(f"Ofwat boundary validation failed: {error}")
        return 1

    invalid_ids = ", ".join(str(item.source_id) for item in report.invalid_geometries)

    print(f"Dataset:    {report.dataset}")
    print(f"Release:    {report.release}")
    print(f"Records:    {report.record_count}")
    print(f"EPSG:       {report.epsg}")
    print(f"Geometries: {report.geometry_types}")
    print(f"Invalid:    {len(report.invalid_geometries)} ({invalid_ids})")
    print(f"Empty:      {len(report.empty_geometry_ids)}")
    print(f"Canonical load eligible: {'yes' if report.canonical_load_eligible else 'no'}")
    print(f"Report:     {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
