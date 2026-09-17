"""Tests for diagnostic Ofwat geometry repair assessment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from watergeo.ingestion.ofwat_boundary_repair_assessment import (
    ASSESSMENT_STATUS,
    BoundaryRepairAssessmentError,
    BoundaryRepairAssessmentReport,
    assess_invalid_geometry,
    write_repair_assessment,
)


def _bow_tie() -> Polygon:
    return Polygon(
        [
            (0, 0),
            (10, 10),
            (0, 10),
            (10, 0),
            (0, 0),
        ]
    )


def test_invalid_geometry_produces_three_diagnostic_candidates() -> None:
    assessment = assess_invalid_geometry(
        123,
        _bow_tie(),
    )

    assert assessment.source_id == 123
    assert assessment.original.valid is False
    assert assessment.original.invalid_reason

    assert [candidate.candidate_id for candidate in assessment.candidates] == [
        "linework",
        "structure_keep",
        "structure_drop",
    ]

    assert len(assessment.comparisons) == 3

    for candidate in assessment.candidates:
        assert candidate.valid is True
        assert candidate.empty is False
        assert candidate.wkb_sha256


def test_assessment_does_not_mark_candidate_as_approved() -> None:
    assessment = assess_invalid_geometry(
        123,
        _bow_tie(),
    )

    assert all(
        not hasattr(
            candidate,
            "approved",
        )
        for candidate in assessment.candidates
    )


def test_valid_geometry_is_not_a_repair_target() -> None:
    valid = Polygon(
        [
            (0, 0),
            (0, 10),
            (10, 10),
            (10, 0),
            (0, 0),
        ]
    )

    with pytest.raises(
        BoundaryRepairAssessmentError,
        match="already valid",
    ):
        assess_invalid_geometry(
            123,
            valid,
        )


def test_deterministic_report_has_no_approval_or_timestamp(
    tmp_path: Path,
) -> None:
    feature = assess_invalid_geometry(
        123,
        _bow_tie(),
    )

    report = BoundaryRepairAssessmentReport(
        assessment_version="test-v1",
        assessment_status=ASSESSMENT_STATUS,
        dataset="test",
        release="test",
        source_sha256="a" * 64,
        target_source_ids=(123,),
        shapely_version="test",
        geos_version="test",
        geometry_hash_encoding="test",
        features=(feature,),
    )

    output_root = tmp_path / "assessment"

    first_path = write_repair_assessment(
        report,
        output_root=output_root,
    )

    first_bytes = first_path.read_bytes()

    second_path = write_repair_assessment(
        report,
        output_root=output_root,
    )

    assert second_path.read_bytes() == first_bytes

    decoded = json.loads(first_bytes)

    assert decoded["assessment_status"] == "diagnostic_only_not_approved"
    assert "generated_at" not in decoded
    assert "approved" not in first_bytes.decode("utf-8").replace(
        "not_approved",
        "",
    )
