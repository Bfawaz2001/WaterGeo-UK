"""Assess candidate repairs for the five invalid Ofwat water-supply polygons."""

from watergeo.ingestion.ofwat_boundary_repair_assessment import (
    BoundaryRepairAssessmentError,
    build_reviewed_repair_assessment,
    write_repair_assessment,
)


def main() -> int:
    try:
        report = build_reviewed_repair_assessment()
        report_path = write_repair_assessment(report)
    except BoundaryRepairAssessmentError as error:
        print(f"Ofwat repair assessment failed: {error}")
        return 1

    print(f"Assessment: {report.assessment_version}")
    print(f"Status:     {report.assessment_status}")
    print(f"Source:     {report.source_sha256}")
    print(f"Shapely:    {report.shapely_version}")
    print(f"GEOS:       {report.geos_version}")

    for feature in report.features:
        print()
        print(f"Source ID {feature.source_id}: {feature.original.invalid_reason}")

        for candidate in feature.candidates:
            print(
                "  "
                f"{candidate.candidate_id}: "
                f"type={candidate.geometry_type}, "
                f"valid={candidate.valid}, "
                f"parts={candidate.part_count}, "
                f"area={candidate.area_m2:.6f}, "
                f"checks={candidate.meets_geometry_checks}"
            )

        for comparison in feature.comparisons:
            print(
                "  compare "
                f"{comparison.left_candidate} vs "
                f"{comparison.right_candidate}: "
                f"equal={comparison.topologically_equal}, "
                "symmetric_difference="
                f"{comparison.symmetric_difference_area_m2:.6f} m², "
                "hausdorff="
                f"{comparison.hausdorff_distance_m:.6f} m, "
                "probes="
                f"{len(comparison.difference_probe_points)}"
            )

    print()
    print("No candidate is approved by this assessment.")
    print(f"Report:     {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
