"""Evidence about repair ambiguity, using synthetic shapes and the read-only role.

These tests do not approve repaired source data or enable automatic repair.
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from watergeo.core.config import Settings
from watergeo.db.engine import create_database_engine

EXPERIMENT = Path(__file__).parents[1] / "fixtures" / "geometry_repairs.sql"


@pytest.fixture(scope="module")
def repairs() -> dict[tuple[str, str], dict[str, Any]]:
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(EXPERIMENT.read_text())).mappings().all()
        return {(row["case_id"], row["method"]): dict(row) for row in rows}
    finally:
        engine.dispose()


def test_candidate_validity_is_not_evidence_of_coverage_accuracy(repairs) -> None:
    assert len(repairs) == 18
    assert all(row["candidate_valid"] for row in repairs.values())
    assert all(row["candidate_srid"] == 27700 for row in repairs.values())
    assert all(row["candidate_dimensions"] == 2 for row in repairs.values())
    # An output can be valid but fail the area table's type/emptiness checks.
    assert not repairs["collapsed_polygon", "structure_drop"]["meets_geometry_checks_after_multi"]


@pytest.mark.parametrize("method", ["linework", "structure_keep", "structure_drop"])
def test_valid_hole_retains_coverage(repairs, method: str) -> None:
    row = repairs["valid_hole", method]
    assert row["original_valid"]
    assert row["candidate_area_m2"] == pytest.approx(96)
    assert row["meets_geometry_checks_after_multi"]
    assert row["repair_is_topologically_idempotent"]
    if method == "linework":
        assert row["coordinates_unchanged"]


@pytest.mark.parametrize("method", ["linework", "structure_keep", "structure_drop"])
def test_self_intersection_has_no_trustworthy_original_area(repairs, method: str) -> None:
    row = repairs["bow_tie", method]
    assert not row["original_valid"]
    assert row["original_area_untrusted_m2"] == 0
    assert row["candidate_area_m2"] == pytest.approx(50)
    assert row["candidate_parts"] == 2
    assert row["meets_geometry_checks_after_multi"]


def test_nested_holes_change_point_membership_between_methods(repairs) -> None:
    linework = repairs["nested_holes", "linework"]
    structure = repairs["nested_holes", "structure_keep"]
    assert not linework["original_valid"]
    assert linework["candidate_area_m2"] == pytest.approx(65)
    assert structure["candidate_area_m2"] == pytest.approx(64)
    assert linework["covers_probe_3_5"]
    assert not structure["covers_probe_3_5"]
    assert linework["meets_geometry_checks_after_multi"]
    assert structure["meets_geometry_checks_after_multi"]


def test_overlapping_parts_change_point_membership_between_methods(repairs) -> None:
    linework = repairs["overlapping_parts", "linework"]
    structure = repairs["overlapping_parts", "structure_keep"]
    assert not linework["original_valid"]
    assert linework["candidate_area_m2"] == pytest.approx(24)
    assert structure["candidate_area_m2"] == pytest.approx(28)
    assert not linework["covers_probe_3_3"]
    assert structure["covers_probe_3_3"]


@pytest.mark.parametrize("method", ["linework", "structure_keep"])
def test_collapsed_polygon_becomes_non_area_geometry(repairs, method: str) -> None:
    row = repairs["collapsed_polygon", method]
    assert row["has_lower_dimension_parts"]
    assert not row["meets_geometry_checks_after_multi"]
    assert not row["candidate_empty"]


def test_dropping_collapsed_parts_can_erase_a_feature(repairs) -> None:
    row = repairs["collapsed_polygon", "structure_drop"]
    assert row["candidate_empty"]
    assert row["candidate_area_m2"] == 0
    assert not row["meets_geometry_checks_after_multi"]


def test_same_area_does_not_mean_no_information_was_lost(repairs) -> None:
    linework = repairs["spike", "linework"]
    structure = repairs["spike", "structure_keep"]
    assert linework["candidate_area_m2"] == structure["candidate_area_m2"] == 100
    assert linework["has_lower_dimension_parts"]
    assert not linework["meets_geometry_checks_after_multi"]
    assert not structure["has_lower_dimension_parts"]
    assert structure["meets_geometry_checks_after_multi"]
