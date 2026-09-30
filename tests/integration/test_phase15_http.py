"""Synthetic integration coverage for Phase 15 national source products."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from test_hydrology_http import engines as engines

from watergeo.api.app import create_app
from watergeo.db.phase15_ingestion import load_snapshot
from watergeo.ingestion.phase15_client import create_bundle
from watergeo.ingestion.phase15_sources import (
    EA_LICENCE,
    normalize_bathing,
    normalize_company_performance,
    normalize_floods,
    normalize_rainfall,
)


def body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def ea(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {"publisher": "Environment Agency", "licence": EA_LICENCE, "version": "0.9"},
        "items": items,
    }


def rainfall_payloads() -> tuple[dict[str, object], dict[str, object]]:
    measure = "http://environment.data.gov.uk/flood-monitoring/id/measures/R1-rainfall"
    return ea(
        [
            {
                "@id": "http://environment.data.gov.uk/flood-monitoring/id/stations/R1",
                "notation": "R1",
                "stationReference": "R1",
                "label": "Test rainfall station",
                "lat": 52.12,
                "long": -1.2,
                "measures": [
                    {"@id": measure, "parameter": "rainfall", "period": 900, "unitName": "mm"}
                ],
            }
        ]
    ), ea([{"measure": {"@id": measure}, "dateTime": "2026-09-28T12:15:00Z", "value": 1.25}])


def flood_payloads() -> tuple[dict[str, object], dict[str, object]]:
    area = {
        "@id": "http://environment.data.gov.uk/flood-monitoring/id/floodAreas/A1",
        "notation": "A1",
        "label": "River Test",
        "description": "Low lying land",
        "county": "Testshire",
        "riverOrSea": "River Test",
        "lat": 51.0,
        "long": -1.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-1.1, 50.9], [-0.9, 50.9], [-0.9, 51.1], [-1.1, 50.9]]],
        },
    }
    warning = {
        "@id": "http://environment.data.gov.uk/flood-monitoring/id/floods/A1",
        "floodAreaID": "A1",
        "description": "River Test warning",
        "severity": "Flood Alert",
        "severityLevel": 3,
        "message": "Publisher text",
        "isTidal": False,
        "timeRaised": "2026-09-28T10:00:00Z",
        "timeMessageChanged": "2026-09-28T10:01:00Z",
        "timeSeverityChanged": "2026-09-28T10:00:00Z",
    }
    return ea([warning]), ea([area])


def bathing_payload() -> dict[str, object]:
    return {
        "format": "linked-data-api",
        "version": "0.2",
        "result": {
            "items": [
                {
                    "_about": "http://environment.data.gov.uk/id/bathing-water/ukx-1",
                    "eubwidNotation": "ukx-1",
                    "name": {"_value": "Test Beach"},
                    "samplingPoint": {"lat": 51.1, "long": -1.2},
                    "latestComplianceAssessment": {
                        "_about": "http://environment.data.gov.uk/data/bathing-water-quality/compliance-rBWD/point/1/year/2025",
                        "complianceClassification": {"name": {"_value": "Good"}},
                    },
                    "latestSampleAssessment": "https://example.invalid/sample/1",
                }
            ]
        },
    }


def bundles(root: Path) -> list[tuple[Path, Any]]:
    stations, readings = rainfall_payloads()
    warnings, areas = flood_payloads()
    company = {
        "publisher": "Ofwat",
        "licence": EA_LICENCE,
        "publication": "WCPR 2024-25",
        "boundary_crosswalk_version": "ofwat-to-water-supply-v1",
        "boundary_crosswalk": {},
        "items": [
            {
                "company_id": "ANH",
                "company_name": "Anglian Water",
                "reporting_period": "2024-25",
                "measure_code": "M1",
                "measure_name": "Published measure",
                "value": 0,
                "value_state": "reported",
                "unit": "count",
                "definition": "Publisher definition",
            }
        ],
    }
    return [
        (
            create_bundle(
                "rainfall",
                {
                    "stations.json": ("https://example.invalid/stations", body(stations), {}),
                    "readings.json": ("https://example.invalid/readings", body(readings), {}),
                },
                lambda value: normalize_rainfall(value["stations.json"], value["readings.json"]),
                root=root,
            ),
            lambda value: normalize_rainfall(value["stations.json"], value["readings.json"]),
        ),
        (
            create_bundle(
                "flood-monitoring",
                {
                    "warnings.json": ("https://example.invalid/warnings", body(warnings), {}),
                    "areas.json": ("https://example.invalid/areas", body(areas), {}),
                },
                lambda value: normalize_floods(value["warnings.json"], value["areas.json"]),
                root=root,
            ),
            lambda value: normalize_floods(value["warnings.json"], value["areas.json"]),
        ),
        (
            create_bundle(
                "bathing-waters",
                {
                    "bathing-waters.json": (
                        "https://example.invalid/bathing",
                        body(bathing_payload()),
                        {},
                    )
                },
                lambda value: normalize_bathing(value["bathing-waters.json"]),
                root=root,
            ),
            lambda value: normalize_bathing(value["bathing-waters.json"]),
        ),
        (
            create_bundle(
                "company-performance",
                {
                    "company-performance.json": (
                        "https://example.invalid/performance",
                        body(company),
                        {},
                    )
                },
                lambda value: normalize_company_performance(value["company-performance.json"]),
                root=root,
            ),
            lambda value: normalize_company_performance(value["company-performance.json"]),
        ),
    ]


def test_phase15_atomic_load_spatial_api_search_and_status(engines, tmp_path: Path) -> None:
    loaded = [
        load_snapshot(engines[0], directory, normalizer)
        for directory, normalizer in bundles(tmp_path)
    ]
    try:
        assert all(result["status"] == "inserted" for result in loaded)
        with TestClient(create_app()) as client:
            rainfall = client.get(
                "/v1/rainfall/stations/near",
                params={"lon": -1.2, "lat": 52.12, "radius_m": 1000},
            )
            assert rainfall.status_code == 200
            assert rainfall.json()["items"][0]["latest_value_mm"] == 1.25
            flood = client.get("/v1/flood-monitoring/warnings")
            assert flood.status_code == 200
            assert flood.json()["items"][0]["severity"] == "Flood Alert"
            bathing = client.get(
                "/v1/bathing-waters/near",
                params={"lon": -1.2, "lat": 51.1, "radius_m": 1000},
            )
            assert bathing.status_code == 200
            assert bathing.json()["items"][0]["classification"] == "Good"
            performance = client.get("/v1/company-performance/companies/ANH")
            assert performance.status_code == 200
            assert performance.json()["item"]["measures"][0]["value"] == 0
            search = client.get("/v1/search", params={"q": "Test", "limit": 24}).json()
            assert "bathing-waters" in {item["kind"] for item in search["items"]}
            flood_search = client.get("/v1/search", params={"q": "River", "limit": 24}).json()
            assert "flood-warnings" in {item["kind"] for item in flood_search["items"]}
            statuses = client.get("/v1/sources/status").json()["sources"]
            phase15 = {
                row["source"]: row
                for row in statuses
                if row["source"]
                in {"rainfall", "flood-monitoring", "bathing-waters", "company-performance"}
            }
            assert set(phase15) == {
                "rainfall",
                "flood-monitoring",
                "bathing-waters",
                "company-performance",
            }
            assert all(row["availability"] == "available" for row in phase15.values())
    finally:
        with engines[2].begin() as connection:
            for table in (
                "company_performance_measure",
                "company_performance_company",
                "bathing_water",
                "flood_warning",
                "flood_area",
                "rainfall_station",
                "national_source_retrieval",
                "national_source_snapshot",
            ):
                connection.execute(text(f"DELETE FROM watergeo.{table}"))  # noqa: S608


def test_rainfall_load_accepts_unlocated_station(engines, tmp_path: Path) -> None:
    stations, readings = rainfall_payloads()
    station = stations["items"][0]  # type: ignore[index]
    station.pop("lat")
    station.pop("long")
    normalize = lambda value: normalize_rainfall(  # noqa: E731
        value["stations.json"], value["readings.json"]
    )
    bundle = create_bundle(
        "rainfall",
        {
            "stations.json": ("https://example.invalid/stations", body(stations), {}),
            "readings.json": ("https://example.invalid/readings", body(readings), {}),
        },
        normalize,
        root=tmp_path,
    )
    loaded = load_snapshot(engines[0], bundle, normalize)
    try:
        with engines[1].connect() as connection:
            unlocated = connection.execute(
                text("""
                    SELECT geom IS NULL FROM watergeo.rainfall_station
                    WHERE snapshot_id=:snapshot AND station_id='R1'
                """),
                {"snapshot": loaded["snapshot_id"]},
            ).scalar_one()
        assert unlocated is True
    finally:
        with engines[2].begin() as connection:
            connection.execute(
                text("DELETE FROM watergeo.rainfall_station WHERE snapshot_id=:snapshot"),
                {"snapshot": loaded["snapshot_id"]},
            )
            connection.execute(
                text("DELETE FROM watergeo.national_source_retrieval WHERE snapshot_id=:snapshot"),
                {"snapshot": loaded["snapshot_id"]},
            )
            connection.execute(
                text("DELETE FROM watergeo.national_source_snapshot WHERE id=:snapshot"),
                {"snapshot": loaded["snapshot_id"]},
            )


def test_identical_content_records_new_retrieval_and_advances_freshness(
    engines, tmp_path: Path
) -> None:
    stations, readings = rainfall_payloads()
    normalize = lambda value: normalize_rainfall(  # noqa: E731
        value["stations.json"], value["readings.json"]
    )
    first_bundle = create_bundle(
        "rainfall",
        {
            "stations.json": ("https://example.invalid/stations", body(stations), {}),
            "readings.json": ("https://example.invalid/readings", body(readings), {}),
        },
        normalize,
        root=tmp_path,
    )
    second_bundle = create_bundle(
        "rainfall",
        {
            "stations.json": ("https://example.invalid/stations", body(stations), {}),
            "readings.json": ("https://example.invalid/readings", body(readings), {}),
        },
        normalize,
        root=tmp_path,
    )
    first = load_snapshot(engines[0], first_bundle, normalize)
    second = load_snapshot(engines[0], second_bundle, normalize)
    try:
        assert first["status"] == "inserted"
        assert second["status"] == "existing"
        assert second["snapshot_id"] == first["snapshot_id"]
        assert second["retrieval_id"] != first["retrieval_id"]
        with engines[1].connect() as connection:
            snapshots = connection.execute(
                text("""
                    SELECT count(*),min(content_sha256),max(content_sha256)
                    FROM watergeo.national_source_snapshot WHERE source_key='rainfall'
                """)
            ).one()
            retrievals = connection.execute(
                text("""
                    SELECT id,retrieval_completed_at FROM watergeo.national_source_retrieval
                    WHERE snapshot_id=:snapshot ORDER BY retrieval_completed_at,id
                """),
                {"snapshot": first["snapshot_id"]},
            ).all()
        assert snapshots[0] == 1
        assert snapshots[1] == snapshots[2]
        assert len(retrievals) == 2
        assert retrievals[1].retrieval_completed_at > retrievals[0].retrieval_completed_at
        with TestClient(create_app()) as client:
            dataset = client.get("/v1/rainfall/dataset").json()
            status = next(
                row
                for row in client.get("/v1/sources/status").json()["sources"]
                if row["source"] == "rainfall"
            )
        assert dataset["snapshot_id"] == first["snapshot_id"]
        assert dataset["retrieval_id"] == second["retrieval_id"]
        assert dataset["content_sha256"] == snapshots[1]
        assert status["retrieved_at"] == dataset["retrieval_completed_at"]
    finally:
        with engines[2].begin() as connection:
            connection.execute(
                text("DELETE FROM watergeo.rainfall_station WHERE snapshot_id=:snapshot"),
                {"snapshot": first["snapshot_id"]},
            )
            connection.execute(
                text("DELETE FROM watergeo.national_source_retrieval WHERE snapshot_id=:snapshot"),
                {"snapshot": first["snapshot_id"]},
            )
            connection.execute(
                text("DELETE FROM watergeo.national_source_snapshot WHERE id=:snapshot"),
                {"snapshot": first["snapshot_id"]},
            )
