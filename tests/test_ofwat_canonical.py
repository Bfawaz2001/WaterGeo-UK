"""Tests for the reviewed Ofwat canonical transformation policy."""

import pytest
from shapely.geometry import Point, Polygon

from watergeo.ingestion.ofwat_canonical import (
    APPROVED_GEOMETRY_CONTRACTS,
    APPROVED_REPAIR_IDS,
    TRANSFORMATION_KEEP_COLLAPSED,
    TRANSFORMATION_METHOD,
    TRANSFORMATION_VERSION,
    CanonicalIngestionError,
    canonicalise_source_geometry,
)


def _valid_square() -> Polygon:
    return Polygon(
        [
            (0, 0),
            (10, 0),
            (10, 10),
            (0, 10),
            (0, 0),
        ]
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


def test_valid_unreviewed_polygon_passes_without_repair() -> None:
    canonical, provenance = canonicalise_source_geometry(
        9999,
        _valid_square(),
    )

    assert canonical.geom_type == "MultiPolygon"
    assert canonical.is_valid
    assert len(canonical.geoms) == 1
    assert provenance is None


def test_invalid_unapproved_geometry_fails_closed() -> None:
    with pytest.raises(
        CanonicalIngestionError,
        match="no approved transformation",
    ):
        canonicalise_source_geometry(
            9999,
            _bow_tie(),
        )


def test_approved_id_requires_exact_source_hash() -> None:
    with pytest.raises(
        CanonicalIngestionError,
        match="reviewed WKB hash",
    ):
        canonicalise_source_geometry(
            1,
            _bow_tie(),
        )


def test_approved_id_cannot_unexpectedly_become_valid() -> None:
    with pytest.raises(
        CanonicalIngestionError,
        match="unexpectedly became valid",
    ):
        canonicalise_source_geometry(
            1,
            _valid_square(),
        )


def test_non_polygon_geometry_is_rejected() -> None:
    with pytest.raises(
        CanonicalIngestionError,
        match="not polygonal",
    ):
        canonicalise_source_geometry(
            9999,
            Point(1, 2),
        )


def test_repair_policy_is_exactly_bounded() -> None:
    assert {
        1,
        4,
        6,
        28,
        30,
    } == APPROVED_REPAIR_IDS

    assert set(APPROVED_GEOMETRY_CONTRACTS) == set(APPROVED_REPAIR_IDS)

    assert TRANSFORMATION_METHOD == "structure"
    assert TRANSFORMATION_KEEP_COLLAPSED is False

    assert TRANSFORMATION_VERSION == "ofwat-water-supply-v1_5-structure-v1"


def test_reviewed_hash_contract_is_complete() -> None:
    expected_parts = {
        1: 3,
        4: 607,
        6: 16,
        28: 12,
        30: 2,
    }

    for source_id, contract in APPROVED_GEOMETRY_CONTRACTS.items():
        assert len(contract.source_wkb_sha256) == 64

        assert len(contract.canonical_wkb_sha256) == 64

        assert contract.canonical_type == "MultiPolygon"

        assert contract.canonical_parts == expected_parts[source_id]
