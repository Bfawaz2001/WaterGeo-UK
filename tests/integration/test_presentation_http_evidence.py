"""Diagnostic-only PostGIS assessment on a complete, invented snapshot."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from watergeo.api.app import create_app, get_database
from watergeo.core.config import MigrationSettings, Settings
from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION
from watergeo.db.engine import create_database_engine
from watergeo.db.presentation_assessment import (
    PresentationAssessmentError,
    assess_presentation,
    canonical_digest,
    inspect_candidate,
)

# Invented hole touching an exterior edge at one point. Valid in BNG; its
# separately transformed point can cross the transformed straight exterior edge.
TOUCHING_HOLE = (
    "MULTIPOLYGON(((500000 200000,501000 200000,501000 201000,500000 201000,500000 200000),"
    "(500000 200500,500500 200250,500500 200750,500000 200500)),"
    "((502000 200000,502100 200000,502100 200100,502000 200100,502000 200000)))"
)


@pytest.fixture(scope="module")
def dataset():
    command.upgrade(Config("alembic.ini"), "head")
    writer = create_database_engine(MigrationSettings())
    runtime = create_database_engine(Settings(), statement_timeout_ms=60_000)
    snapshot = uuid4()
    try:
        with writer.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO watergeo.water_supply_snapshot
                (id, source_sha256, source_url, source_bytes, retrieved_at, publisher,
                 distributor, licence_name, licence_url, attribution, transformation_version)
                VALUES (:id, :sha, 'https://example.invalid/synthetic.zip', 1, now(),
                        'Synthetic', 'Synthetic', 'Synthetic', 'https://example.invalid/licence',
                        'Synthetic test only', :version)
            """),
                {
                    "id": snapshot,
                    "sha": OFWAT_WATER_SUPPLY_SHA256,
                    "version": OFWAT_WATER_SUPPLY_TRANSFORMATION,
                },
            )
            connection.execute(
                text("""
                INSERT INTO watergeo.water_supply_area(snapshot_id, source_id, source_fields, geom)
                SELECT :snapshot, n, jsonb_build_object('synthetic', true),
                    CASE WHEN n IN (3,7) THEN public.ST_GeomFromText(:wkt, 27700)
                    ELSE public.ST_Multi(public.ST_MakeEnvelope(400000,200000,400100,200100,27700))
                    END FROM generate_series(1,1141) n
            """),
                {"snapshot": snapshot, "wkt": TOUCHING_HOLE},
            )
        yield runtime, snapshot
    finally:
        with writer.begin() as connection:
            connection.execute(
                text("DELETE FROM watergeo.water_supply_area WHERE snapshot_id=:id"),
                {"id": snapshot},
            )
            connection.execute(
                text("DELETE FROM watergeo.water_supply_snapshot WHERE id=:id"), {"id": snapshot}
            )
        writer.dispose()
        runtime.dispose()


def test_full_assessment_discovers_failures_and_preserves_canonical_rows(dataset):
    runtime, snapshot = dataset
    with runtime.connect() as connection:
        before = canonical_digest(connection, snapshot)
    report = assess_presentation(runtime)
    assert len(report["baseline"]) == 1141
    assert report["failed_source_ids"] == [3, 7]
    assert report["runtime"]["transaction_read_only"] == "on"
    assert report["status"] == "diagnostic_only_not_approved"
    assert report["canonical_rows_sha256_before"] == before
    assert report["canonical_rows_sha256_after"] == before
    with runtime.connect() as connection:
        assert canonical_digest(connection, snapshot) == before
    candidates = {row["candidate"]: row for row in report["features"][0]["candidates"]}
    assert not candidates["direct"]["output"]["output_valid"]
    for name in ("structure_drop", "linework"):
        output = candidates[name]["output"]
        assert output["output_valid"]
        assert output["roundtrip_valid"]
        assert output["boundary_hausdorff_m"] >= 0
        assert output["symmetric_difference_m2"] >= 0
        assert len(output["output_wkb_sha256"]) == 64
        assert output["within_api_byte_limit"]


def test_candidate_hashes_repeat_and_preserve_hole_measurements(dataset):
    runtime, snapshot = dataset
    with runtime.connect() as connection:
        first = inspect_candidate(connection, snapshot, 3, "structure_drop")
        second = inspect_candidate(connection, snapshot, 3, "structure_drop")
        assert first == second
        assert first["canonical"]["holes"] == 1
        assert first["output"]["hole_count_delta"] == -1


def test_vertex_budget_skips_before_segmentizing(dataset, monkeypatch):
    runtime, snapshot = dataset
    monkeypatch.setattr("watergeo.db.presentation_assessment.MAX_CANDIDATE_POINTS", 1)
    with runtime.connect() as connection:
        result = inspect_candidate(connection, snapshot, 3, "segmentize_1m")
    assert result["status"] == "skipped_vertex_budget"
    assert "output" not in result


def test_missing_reviewed_snapshot_fails_without_falling_back(dataset, monkeypatch):
    runtime, _ = dataset
    monkeypatch.setattr("watergeo.db.presentation_assessment.OFWAT_WATER_SUPPLY_SHA256", "f" * 64)
    with pytest.raises(PresentationAssessmentError, match="not loaded"):
        assess_presentation(runtime)


@pytest.mark.parametrize("mismatch", [None, "canonical", "output"])
def test_http_presentation_exception_requires_both_reviewed_hashes(dataset, monkeypatch, mismatch):
    runtime, snapshot = dataset
    with runtime.connect() as connection:
        before = canonical_digest(connection, snapshot)
        candidate = inspect_candidate(connection, snapshot, 3, "structure_drop")
    canonical_hash = candidate["canonical"]["wkb_sha256"]
    output_hash = candidate["output"]["geojson_sha256"]
    if mismatch == "canonical":
        canonical_hash = "0" * 64
    if mismatch == "output":
        output_hash = "0" * 64
    # Invented geometry gets an invented contract in this test only. Production
    # contracts contain hashes of the four reviewed publisher geometries.
    monkeypatch.setattr(
        "watergeo.db.water_supply.REVIEWED_WGS84_GEOMETRIES", {3: (canonical_hash, output_hash)}
    )
    app = create_app()
    app.dependency_overrides[get_database] = lambda: runtime
    with TestClient(app) as client:
        metadata = client.get("/v1/water-supply/dataset").json()
        assert metadata["transformation_version"] == OFWAT_WATER_SUPPLY_TRANSFORMATION
        assert metadata["presentation_version"] == "ofwat-water-supply-v1_5-wgs84-structure-v1"
        assert metadata["presentation_exception_source_ids"] == [3, 4, 16, 21]
        response = client.get("/v1/water-supply/areas/3/geometry")
        if mismatch:
            assert response.status_code == 503
            assert response.json() == {"detail": "Water-supply dataset unavailable"}
        else:
            assert response.status_code == 200
            presentation = response.json()["presentation"]
            assert presentation["method"] == "post_transform_structure"
            assert presentation["canonical_geometry_changed"] is False
            assert presentation["canonical_wkb_sha256"] == canonical_hash
            assert presentation["geometry_geojson_sha256"] == output_hash
            assert response.json()["properties"]["transformation"] is None
        # Identical canonical geometry with a different ID is never repaired.
        assert client.get("/v1/water-supply/areas/7/geometry").status_code == 503
        plain = client.get("/v1/water-supply/areas/1/geometry")
        assert plain.status_code == 200
        assert plain.json()["presentation"]["method"] == "reprojection"
        assert plain.json()["presentation"]["canonical_wkb_sha256"] is None
    with runtime.connect() as connection:
        assert canonical_digest(connection, snapshot) == before
