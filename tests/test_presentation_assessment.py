"""Geometric meaning and bounds of offline assessment measurements."""

import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import shapely
from shapely.geometry import MultiPolygon, Polygon, box

from watergeo.core.presentation import (
    REVIEWED_WGS84_GEOJSON_VARIANTS,
    REVIEWED_WGS84_GEOMETRIES,
    WGS84_PRESENTATION_VERSION,
)
from watergeo.db.presentation_assessment import (
    PresentationAssessmentError,
    boundary_hausdorff,
    component_correspondence,
    inspect_candidate,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (box(0, 0, 10, 10), box(1, 2, 11, 12)),
        (box(0, 0, 10, 10), box(0, 0, 10, 10)),
        (
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(2, 2), (3, 2), (3, 3)]]),
            box(0, 0, 10, 10),
        ),
        (MultiPolygon([box(0, 0, 1, 1), box(3, 3, 5, 5)]), box(0, 0, 5, 5)),
    ],
)
def test_indexed_boundary_metric_matches_geos_discrete_hausdorff(left, right):
    expected = shapely.hausdorff_distance(left.boundary, right.boundary)
    assert boundary_hausdorff(left, right) == pytest.approx(expected)
    assert boundary_hausdorff(right, left) == pytest.approx(expected)


def test_empty_geometry_has_no_fabricated_zero_distance():
    with pytest.raises(PresentationAssessmentError, match="empty boundary"):
        boundary_hausdorff(Polygon(), box(0, 0, 1, 1))


def test_component_correspondence_distinguishes_splits_from_missing_parts():
    before = MultiPolygon([box(0, 0, 10, 10), box(20, 20, 21, 21)])
    after = MultiPolygon([box(0, 0, 4, 10), box(6, 0, 10, 10), box(30, 30, 31, 31)])
    result = component_correspondence(before, after)
    assert result == {
        "canonical_parts_without_candidate_intersection": 1,
        "candidate_parts_without_canonical_intersection": 1,
        "canonical_parts_intersecting_multiple_candidates": 1,
        "candidate_parts_intersecting_multiple_canonical": 0,
    }


def test_unknown_candidate_rejected_before_sql():
    connection = MagicMock()
    with pytest.raises(ValueError, match="Unknown presentation candidate"):
        inspect_candidate(connection, uuid4(), 3, "geom); DROP TABLE x;")
    connection.execute.assert_not_called()


def test_presentation_contract_is_separate_and_limited_to_reviewed_ids():
    assert set(REVIEWED_WGS84_GEOMETRIES) == {3, 4, 16, 21}
    report = json.loads(
        Path("docs/data-sources/ofwat-water-supply-presentation-assessment.json").read_text()
    )
    assert report["baseline_summary"]["area_count"] == 1141
    assert report["canonical_rows_sha256_before"] == report["canonical_rows_sha256_after"]
    for feature in report["features"]:
        candidate = next(c for c in feature["candidates"] if c["candidate"] == "structure_drop")
        assert REVIEWED_WGS84_GEOMETRIES[feature["source_id"]] == (
            candidate["canonical"]["wkb_sha256"],
            candidate["output"]["geojson_sha256"],
        )
        assert candidate["output"]["output_valid"]
        assert candidate["output"]["hole_count_delta"] == 0
        assert not candidate["output"]["lower_dimension_parts"]


def test_cross_platform_presentation_variants_are_exactly_reviewed():
    evidence = json.loads(
        Path("docs/data-sources/ofwat-water-supply-presentation-cross-platform.json").read_text()
    )
    assert evidence["policy_version"] == WGS84_PRESENTATION_VERSION
    assert set(REVIEWED_WGS84_GEOJSON_VARIANTS) == set(REVIEWED_WGS84_GEOMETRIES)
    for feature in evidence["features"]:
        source_id = feature["source_id"]
        assert feature["canonical_wkb_sha256"] == REVIEWED_WGS84_GEOMETRIES[source_id][0]
        assert feature["arm64"]["geojson_sha256"] == REVIEWED_WGS84_GEOMETRIES[source_id][1]
        assert (feature["amd64"]["geojson_sha256"],) == REVIEWED_WGS84_GEOJSON_VARIANTS[source_id]
        for runtime in ("arm64", "amd64"):
            output = feature[runtime]
            assert output["output_valid"] and output["roundtrip_valid"]
            assert output["hole_count_delta"] == 0
