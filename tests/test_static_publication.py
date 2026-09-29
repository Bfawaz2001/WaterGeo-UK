import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx2 as httpx
import pytest

from watergeo.static_publication import ApiReader, StaticPublicationError, build_publication

SNAPSHOT = "00000000-0000-0000-0000-000000000015"
COMMIT = "a" * 40


def dataset(name: str = "fixture") -> dict[str, str]:
    return {
        "dataset": name,
        "snapshot_id": SNAPSHOT,
        "publisher": "Fixture publisher",
        "retrieval_completed_at": "2026-09-28T10:00:00Z",
        "licence": "Open Government Licence",
        "attribution": "Fixture publisher",
        "normalization_version": "fixture-v1",
    }


def fixture_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    query = parse_qs(request.url.query.decode())
    if path == "/v1/sources/status":
        return httpx.Response(200, json={"checked_at": "variable", "sources": []})
    if path == "/v1/flood-monitoring/dataset":
        return httpx.Response(200, json=dataset("flood"))
    if path == "/v1/flood-monitoring/areas":
        return httpx.Response(
            200,
            json={
                "dataset": dataset("flood"),
                "items": [
                    {
                        "area_id": "area-1",
                        "label": "Fixture flood area",
                        "county": "Fixture county",
                        "geometry": {"type": "Polygon", "coordinates": []},
                    }
                ],
            },
        )
    if path == "/v1/company-performance/dataset":
        return httpx.Response(200, json=dataset("performance"))
    if path == "/v1/company-performance/companies":
        return httpx.Response(
            200,
            json={"dataset": dataset("performance"), "items": [{"company_id": "C1"}]},
        )
    if path == "/v1/company-performance/companies/C1":
        return httpx.Response(
            200,
            json={
                "dataset": dataset("performance"),
                "item": {
                    "company_id": "C1",
                    "company_name": "Fixture Water",
                    "boundary_company_acronym": None,
                    "measures": [
                        {
                            "reporting_period": "2024-25",
                            "measure_code": "M1",
                            "measure_name": "Fixture measure",
                            "value": 0,
                            "value_state": "reported",
                            "unit": "count",
                            "definition": "Fixture definition",
                            "publication": "Fixture publication",
                        }
                    ],
                },
            },
        )
    if path == "/v1/water-supply/dataset":
        return httpx.Response(200, json={**dataset("supply"), "area_count": 1})
    if path == "/v1/water-supply/areas":
        return httpx.Response(
            200,
            json={"snapshot_id": SNAPSHOT, "items": [{"source_id": 1}], "next_after_id": None},
        )
    if path == "/v1/water-supply/areas/1/geometry":
        return httpx.Response(
            200,
            json={"type": "Feature", "id": 1, "geometry": {"type": "Polygon", "coordinates": []}},
        )
    if path == "/v1/catchments/water-bodies/WB1/geometry":
        return httpx.Response(
            200,
            json={
                "snapshot_id": SNAPSHOT,
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "WB1",
                        "geometry": {"type": "Polygon", "coordinates": []},
                    }
                ],
            },
        )

    identities = {
        "/v1/hydrology/stations": ("station_id", "H1"),
        "/v1/water-quality/sampling-points": ("sampling_point_id", "Q1"),
        "/v1/severn-trent/reservoir-levels/reservoirs": ("reservoir_id", "R1"),
        "/v1/thames-water/discharge-status/sites": ("site_id", "T1"),
        "/v1/rainfall/stations": ("station_id", "RF1"),
        "/v1/bathing-waters": ("bathing_water_id", "B1"),
        "/v1/catchments/water-bodies": ("water_body_id", "WB1"),
    }
    if path in identities:
        identity, value = identities[path]
        assert query.get("limit") == ["100"]
        return httpx.Response(
            200,
            json={
                "dataset": dataset(path),
                "items": [{identity: value, "name": value, "longitude": -1.0, "latitude": 52.0}],
                "next_after_id": None,
            },
        )
    return httpx.Response(404, json={"detail": path})


def reader() -> ApiReader:
    return ApiReader("http://127.0.0.1:8000", transport=httpx.MockTransport(fixture_response))


def test_publication_is_deterministic_complete_and_refuses_overwrite(tmp_path: Path) -> None:
    api = reader()
    first = build_publication(api, tmp_path / "first", COMMIT)
    second = build_publication(api, tmp_path / "second", COMMIT)
    assert first == second
    assert first["publication_id"] == second["publication_id"]
    assert str(tmp_path) not in json.dumps(first)
    assert first["sources"]["rainfall"]["snapshot_id"] == SNAPSHOT
    assert set(first["sources"]) == {
        "hydrology",
        "water-quality",
        "reservoir-levels",
        "thames-discharge",
        "rainfall",
        "bathing-waters",
        "catchments",
        "flood-warnings",
        "company-performance",
        "water-supply",
    }
    assert first["files"]["datasets/catchments/water-bodies.geojson"]["count"] == 1
    for relative, metadata in first["files"].items():
        body = (tmp_path / "first" / relative).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(body).hexdigest()
    published = json.dumps(first)
    assert "postgresql://" not in published
    assert "PASSWORD" not in published
    with pytest.raises(StaticPublicationError, match="already exists"):
        build_publication(api, tmp_path / "first", COMMIT)
    api.close()


def test_publication_fails_if_a_page_changes_snapshot(tmp_path: Path) -> None:
    def changed(request: httpx.Request) -> httpx.Response:
        response = fixture_response(request)
        if request.url.path == "/v1/rainfall/stations":
            body = json.loads(response.content)
            body["dataset"]["snapshot_id"] = "00000000-0000-0000-0000-000000000099"
            return httpx.Response(200, json=body)
        return response

    api = ApiReader("http://localhost:8000", transport=httpx.MockTransport(changed))
    # The first page establishes its own source snapshot; a changed later page is what must fail.
    original = fixture_response
    calls = 0

    def paged_change(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/v1/rainfall/stations":
            calls += 1
            value = json.loads(original(request).content)
            if calls == 1:
                value["next_after_id"] = "RF1"
            else:
                value["dataset"]["snapshot_id"] = "00000000-0000-0000-0000-000000000099"
                value["items"] = []
            return httpx.Response(200, json=value)
        return original(request)

    api.close()
    api = ApiReader("http://localhost:8000", transport=httpx.MockTransport(paged_change))
    with pytest.raises(StaticPublicationError, match="snapshot changed"):
        build_publication(api, tmp_path / "changed", COMMIT)
    assert not (tmp_path / "changed").exists()
    api.close()


def test_api_reader_rejects_remote_build_source() -> None:
    with pytest.raises(StaticPublicationError, match="local build service"):
        ApiReader("https://example.com")


def test_publication_rejects_missing_source_provenance(tmp_path: Path) -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        response = fixture_response(request)
        if request.url.path == "/v1/rainfall/stations":
            body = json.loads(response.content)
            body["dataset"].pop("licence")
            return httpx.Response(200, json=body)
        return response

    api = ApiReader("http://localhost:8000", transport=httpx.MockTransport(missing))
    with pytest.raises(StaticPublicationError, match="licence provenance"):
        build_publication(api, tmp_path / "missing", COMMIT)
    assert not (tmp_path / "missing").exists()
    api.close()


def test_optional_analytical_outputs_preserve_snapshot_metadata(tmp_path: Path) -> None:
    parquet = pytest.importorskip("pyarrow.parquet")
    api = reader()
    manifest = build_publication(api, tmp_path / "analytics", COMMIT, analytics=True)
    expected = {
        "analytics/rainfall.parquet",
        "analytics/bathing-waters.parquet",
        "analytics/flood-areas.parquet",
        "analytics/company-performance.parquet",
    }
    assert expected <= set(manifest["files"])
    rainfall = parquet.read_table(tmp_path / "analytics/analytics/rainfall.parquet")
    assert rainfall.column("snapshot_id").to_pylist() == [SNAPSHOT]
    assert json.loads(rainfall.schema.metadata[b"geo"])["version"] == "1.1.0"
    performance = parquet.read_table(tmp_path / "analytics/analytics/company-performance.parquet")
    assert performance.column("value").to_pylist() == [0]
    api.close()
