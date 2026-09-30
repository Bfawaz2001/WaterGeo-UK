import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2 as httpx
import pytest
from shapely import make_valid
from shapely.geometry import shape

import watergeo.ingestion.phase15_sources as phase15_sources
from watergeo.ingestion.phase15_client import (
    create_bundle,
    fetch_flood_monitoring,
    fetch_rainfall,
    read_bundle,
)
from watergeo.ingestion.phase15_sources import (
    EA_LICENCE,
    Phase15SourceError,
    normalize_bathing,
    normalize_company_performance,
    normalize_floods,
    normalize_rainfall,
)


def ea(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {
            "publisher": "Environment Agency",
            "licence": EA_LICENCE,
            "version": "0.9",
        },
        "items": items,
    }


def rainfall_payloads() -> tuple[dict[str, object], dict[str, object]]:
    measure = "http://environment.data.gov.uk/flood-monitoring/id/measures/R1-rainfall"
    station = {
        "@id": "http://environment.data.gov.uk/flood-monitoring/id/stations/R1",
        "stationReference": "R1",
        "notation": "R1",
        "label": "Rainfall station",
        "lat": 52.12,
        "long": -1.2,
        "gridReference": "SP000000",
        "measures": [
            {
                "@id": measure,
                "parameter": "rainfall",
                "period": 900,
                "unitName": "mm",
            }
        ],
    }
    reading = {
        "measure": {"@id": measure},
        "dateTime": "2026-09-28T12:15:00Z",
        "value": 1.25,
    }
    return ea([station]), ea([reading])


def test_rainfall_preserves_privacy_and_measurement_time() -> None:
    stations, readings = rainfall_payloads()
    product = normalize_rainfall(stations, readings)  # type: ignore[arg-type]
    assert product.entities[0]["display_name"] is None
    assert product.entities[0]["latitude"] == 52.12
    assert product.entities[0]["latest_value_mm"] == 1.25
    assert product.entities[0]["latest_observed_at"] == "2026-09-28T12:15:00+00:00"


def test_rainfall_rejects_schema_licence_and_timestamp_drift() -> None:
    stations, readings = rainfall_payloads()
    stations["meta"]["licence"] = "unexpected"  # type: ignore[index]
    with pytest.raises(Phase15SourceError, match="contract changed"):
        normalize_rainfall(stations, readings)  # type: ignore[arg-type]


def test_rainfall_preserves_unlocated_station_and_missing_latest_value() -> None:
    stations, readings = rainfall_payloads()
    station = stations["items"][0]  # type: ignore[index]
    station.pop("lat")
    station.pop("long")
    readings["items"][0].pop("value")  # type: ignore[index]
    product = normalize_rainfall(stations, readings)  # type: ignore[arg-type]
    assert product.entities[0]["latitude"] is None
    assert product.entities[0]["longitude"] is None
    assert product.entities[0]["latest_value_mm"] is None
    stations, readings = rainfall_payloads()
    readings["items"][0]["dateTime"] = "yesterday"  # type: ignore[index]
    with pytest.raises(Phase15SourceError, match="timestamp"):
        normalize_rainfall(stations, readings)  # type: ignore[arg-type]


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


def test_flood_warning_preserves_publisher_severity_and_geometry() -> None:
    warnings, areas = flood_payloads()
    source_geometry = areas["items"][0]["geometry"]  # type: ignore[index]
    product = normalize_floods(warnings, areas)  # type: ignore[arg-type]
    assert product.secondary[0]["severity"] == "Flood Alert"
    assert product.secondary[0]["severity_level"] == 3
    assert product.entities[0]["geometry"] == source_geometry
    assert product.entities[0]["geometry_policy"] == {
        "policy": "source-valid",
        "repaired": False,
    }


def test_flood_warning_rejects_reinterpreted_severity_and_bad_geometry() -> None:
    warnings, areas = flood_payloads()
    warnings["items"][0]["severity"] = "High risk"  # type: ignore[index]
    with pytest.raises(Phase15SourceError, match="severity"):
        normalize_floods(warnings, areas)  # type: ignore[arg-type]


def test_flood_warning_repairs_only_low_distortion_polygon_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings, areas = flood_payloads()
    source_geometry = {  # type: ignore[var-annotated]
        "type": "Polygon",
        "coordinates": [
            [
                [-1.1, 50.9],
                [-0.9, 50.9],
                [-0.9, 51.1],
                [-1.1, 51.1],
                [-1.1, 51.0],
                [-1.09999, 51.0],
                [-1.1, 51.0],
                [-1.1, 50.9],
            ]
        ],
    }
    areas["items"][0]["geometry"] = source_geometry  # type: ignore[index]
    calls: list[dict[str, int]] = []
    actual_to_wkb = phase15_sources.to_wkb

    def tracked_to_wkb(geometry: object, **kwargs: int) -> bytes:
        calls.append(kwargs)
        return actual_to_wkb(geometry, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(phase15_sources, "to_wkb", tracked_to_wkb)
    product = normalize_floods(warnings, areas)  # type: ignore[arg-type]
    entity = product.entities[0]
    policy = entity["geometry_policy"]
    original = shape(source_geometry)
    expected = make_valid(original, method="structure", keep_collapsed=False)
    canonical = shape(entity["geometry"])
    assert canonical.is_valid
    assert canonical.geom_type in {"Polygon", "MultiPolygon"}
    assert canonical.equals(expected)
    assert policy["repaired"] is True
    assert policy["policy"] == "ea-flood-area-structure-canonical-v2"
    assert policy["area_change_square_degrees"] / original.area <= 0.000001
    assert policy["hausdorff_degrees"] <= 0.0001
    assert policy["canonical_wkb_sha256"] == (
        "9c49976a81e68b98647477cc07b106913d3ef940e868330bddd820e4ce62c650"
    )
    assert policy["source_wkb_sha256"] != policy["canonical_wkb_sha256"]
    assert calls == [{"byte_order": 1, "output_dimension": 2}]
    warnings, areas = flood_payloads()
    areas["items"][0]["geometry"] = {"type": "Point", "coordinates": [-1, 51]}  # type: ignore[index]
    with pytest.raises(Phase15SourceError, match="geometry"):
        normalize_floods(warnings, areas)  # type: ignore[arg-type]


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
                        "_about": (
                            "http://environment.data.gov.uk/data/"
                            "bathing-water-quality/compliance-rBWD/point/1/year/2025"
                        ),
                        "complianceClassification": {"name": {"_value": "Good"}},
                    },
                    "latestSampleAssessment": "https://example.invalid/sample/1",
                    "latestRiskPrediction": {"riskLevel": {"name": {"_value": "normal"}}},
                }
            ]
        },
    }


def test_bathing_water_keeps_classification_sample_and_advice_distinct() -> None:
    product = normalize_bathing(bathing_payload())  # type: ignore[arg-type]
    item = product.entities[0]
    assert item["classification"] == "Good"
    assert item["assessment_year"] == 2025
    assert item["latest_sample_uri"].endswith("/sample/1")
    assert item["latest_risk_prediction"]["riskLevel"]["name"]["_value"] == "normal"


def test_bathing_water_preserves_missing_classification() -> None:
    payload = bathing_payload()
    payload["result"]["items"][0].pop("latestComplianceAssessment")  # type: ignore[index]
    item = normalize_bathing(payload).entities[0]  # type: ignore[arg-type]
    assert item["classification"] is None
    assert item["assessment_year"] is None


def test_ofwat_model_distinguishes_zero_missing_and_not_applicable() -> None:
    base = {
        "company_id": "ANH",
        "company_name": "Anglian Water",
        "reporting_period": "2024-25",
        "measure_name": "Published measure",
        "unit": "count",
        "definition": "Publisher definition",
    }
    payload = {
        "publisher": "Ofwat",
        "licence": EA_LICENCE,
        "publication": "WCPR 2024-25",
        "boundary_crosswalk_version": "ofwat-to-water-supply-v1",
        "boundary_crosswalk": {"ANH": "AWS"},
        "items": [
            {**base, "measure_code": "M1", "value": 0, "value_state": "reported"},
            {**base, "measure_code": "M2", "value": None, "value_state": "missing"},
            {**base, "measure_code": "M3", "value": None, "value_state": "not_applicable"},
        ],
    }
    product = normalize_company_performance(payload)
    assert [row["value"] for row in product.secondary] == [0.0, None, None]
    assert product.entities[0]["boundary_company_acronym"] == "AWS"
    assert [row["value_state"] for row in product.secondary] == [
        "reported",
        "missing",
        "not_applicable",
    ]


def test_ofwat_rejects_unreviewed_or_row_level_boundary_mapping() -> None:
    payload = {
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
                "value": 1,
                "value_state": "reported",
                "boundary_company_acronym": "AWS",
            }
        ],
    }
    with pytest.raises(Phase15SourceError, match="reviewed crosswalk"):
        normalize_company_performance(payload)


def test_evidence_is_written_before_validation_and_rejected_bundle_is_not_loadable(
    tmp_path: Path,
) -> None:
    body = json.dumps({"raw": "publisher response"}).encode()

    def reject(_values: dict[str, dict[str, object]]) -> object:
        raise Phase15SourceError("schema changed")

    with pytest.raises(Phase15SourceError, match="schema changed"):
        create_bundle(
            "rainfall",
            {"stations.json": ("https://example.invalid/source", body, {})},
            reject,  # type: ignore[arg-type]
            root=tmp_path,
        )
    directory = next((tmp_path / "rainfall").iterdir())
    assert (directory / "stations.json").read_bytes() == body
    assert (directory / "retrieval.json").is_file()
    assert not (directory / "manifest.json").exists()
    with pytest.raises(Phase15SourceError):
        read_bundle(directory, reject)  # type: ignore[arg-type]


def test_malformed_json_keeps_exact_raw_evidence_and_retrieval_metadata(tmp_path: Path) -> None:
    body = b'{"items":['
    with pytest.raises(Phase15SourceError, match="Malformed source JSON"):
        create_bundle(
            "rainfall",
            {"stations.json": ("https://example.invalid/source", body, {"etag": "v1"})},
            lambda _values: pytest.fail("normalization must not run"),
            root=tmp_path,
        )
    directory = next((tmp_path / "rainfall").iterdir())
    assert (directory / "stations.json").read_bytes() == body
    retrieval = json.loads((directory / "retrieval.json").read_bytes())
    assert retrieval["responses"]["stations.json"]["sha256"]
    assert retrieval["responses"]["stations.json"]["bytes"] == len(body)
    assert not (directory / "manifest.json").exists()


def test_live_retrieval_timestamp_brackets_requests_and_preserves_checksums(tmp_path: Path) -> None:
    stations, readings = rainfall_payloads()
    request_times: list[datetime] = []

    def respond(request: httpx.Request) -> httpx.Response:
        request_times.append(datetime.now(UTC))
        value = stations if request.url.path.endswith("/stations") else readings
        return httpx.Response(200, json=value)

    directory = fetch_rainfall(tmp_path, transport=httpx.MockTransport(respond))
    manifest, product = read_bundle(
        directory,
        lambda values: normalize_rainfall(values["stations.json"], values["readings.json"]),
    )
    started = datetime.fromisoformat(manifest["retrieval_started_at"])
    completed = datetime.fromisoformat(manifest["retrieval_completed_at"])
    assert started <= min(request_times) <= max(request_times) <= completed
    assert product.entities[0]["station_id"] == "R1"
    for name, metadata in manifest["responses"].items():
        assert metadata["sha256"]
        assert metadata["bytes"] == (directory / name).stat().st_size


def test_malformed_flood_warnings_are_persisted_before_decode(tmp_path: Path) -> None:
    malformed = b'{"items":['

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=malformed, headers={"content-type": "application/json"})

    with pytest.raises(Phase15SourceError, match="Malformed source JSON"):
        fetch_flood_monitoring(tmp_path, transport=httpx.MockTransport(respond))
    directory = next((tmp_path / "flood-monitoring").iterdir())
    assert (directory / "warnings.json").read_bytes() == malformed
    retrieval = json.loads((directory / "retrieval.json").read_bytes())
    assert retrieval["evidence_state"] == "retrieving"
    assert retrieval["responses"]["warnings.json"]["sha256"]
    assert not (directory / "manifest.json").exists()


def test_later_flood_request_failure_retains_partial_raw_evidence(tmp_path: Path) -> None:
    warnings, _areas = flood_payloads()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/floods"):
            return httpx.Response(200, json=warnings)
        if request.url.path.endswith("/A1"):
            return httpx.Response(200, json={"items": {"notation": "A1"}})
        return httpx.Response(503, json={"detail": "publisher unavailable"})

    with pytest.raises(Phase15SourceError, match="status"):
        fetch_flood_monitoring(tmp_path, transport=httpx.MockTransport(respond))
    directory = next((tmp_path / "flood-monitoring").iterdir())
    assert (directory / "warnings.json").is_file()
    assert (directory / "area-A1.json").is_file()
    assert not (directory / "polygon-A1.json").exists()
    assert not (directory / "manifest.json").exists()
