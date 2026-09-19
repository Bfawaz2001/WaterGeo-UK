"""Synthetic source tests; never contact the public EA service."""

import json
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from watergeo.api.app import create_app
from watergeo.core.config import Settings
from watergeo.ingestion.hydrology import (
    LICENCE,
    HydrologyError,
    decode,
    location,
    normalize,
    timestamp,
)
from watergeo.ingestion.hydrology_client import (
    check_url,
    fetch_snapshot,
    read_snapshot,
    request_url,
)


def records() -> dict[str, Any]:
    return json.loads(Path("tests/fixtures/hydrology/records.json").read_text())


def responder(request: httpx.Request) -> httpx.Response:
    kind = {"stations": "stations", "measures": "measures", "readings": "observations"}[
        request.url.path.rsplit("/", 1)[1]
    ]
    offset = int(request.url.params["_offset"])
    return httpx.Response(
        200,
        json={
            "meta": {
                "publisher": "Environment Agency",
                "license": LICENCE,
                "version": "2.1.1",
                "limit": 2,
                "offset": offset,
            },
            "items": records()[kind][offset : offset + 2],
        },
        headers={"etag": '"synthetic"'},
    )


def test_round_trip_pagination_manifest_and_hashes(tmp_path: Path) -> None:
    path = fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    manifest, data = read_snapshot(path)
    assert len(manifest["pages"]) == 6
    assert data.counts == {
        "station_count": 3,
        "station_with_location_count": 2,
        "station_without_location_count": 1,
        "measure_count": 3,
        "latest_observation_count": 3,
    }
    assert data.observations[0]["value"] == 0
    assert data.observations[1]["value"] is None
    assert data.observations[0]["observed_at"].endswith("+00:00")
    assert manifest["pages"][0]["headers"]["etag"] == '"synthetic"'
    second = fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    other, normalized = read_snapshot(second)
    assert other["content_sha256"] == manifest["content_sha256"]
    assert normalized.sha256 == data.sha256
    (path / "stations-0.json").write_text("{}")
    with pytest.raises(HydrologyError, match="hash"):
        read_snapshot(path)


@pytest.mark.parametrize(
    "value",
    [
        {"lat": 51},
        {"long": 1},
        {"lat": float("nan"), "long": 1},
        {"lat": 91, "long": 1},
        {"lat": 51, "long": -181},
        {"lat": [51], "long": 1},
        {"lat": True, "long": 1},
        {"lat": "51", "long": 1},
        {"easting": 1},
        {"easting": 1, "northing": 2},
    ],
)
def test_invalid_locations(value: dict[str, Any]) -> None:
    with pytest.raises(HydrologyError):
        location(value)


def test_missing_location_and_absent_observation_are_preserved() -> None:
    assert location({}) == (None, None)
    assert location({"lat": None, "long": None}) == (None, None)
    raw = records()
    raw["observations"] = []
    assert normalize(raw).counts["measure_count"] == 3
    assert normalize(raw).counts["latest_observation_count"] == 0


@pytest.mark.parametrize("kind", ["stations", "measures", "observations"])
def test_duplicate_identities_rejected(kind: str) -> None:
    raw = records()
    raw[kind].append(raw[kind][0])
    with pytest.raises(HydrologyError):
        normalize(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", float("inf")),
        ("value", True),
        ("value", "0"),
        ("dateTime", "2026-01-01"),
        ("dateTime", "2026-02-30T00:00:00"),
        ("value", None),
    ],
)
def test_invalid_observation(field: str, value: Any) -> None:
    raw = records()
    raw["observations"][0][field] = value
    with pytest.raises(HydrologyError):
        normalize(raw)


def test_timezone_contract_and_unknown_relationship() -> None:
    assert timestamp("2020-01-01T12:00:00").isoformat() == "2020-01-01T12:00:00+00:00"
    assert timestamp("2020-01-01T12:00:00+01:00").hour == 11
    raw = records()
    raw["measures"][0]["station"]["@id"] = (
        "http://environment.data.gov.uk/hydrology/id/stations/unknown"
    )
    with pytest.raises(HydrologyError):
        normalize(raw)


@pytest.mark.parametrize(
    "url",
    [
        "http://environment.data.gov.uk/hydrology/id/stations",
        "https://evil.invalid/hydrology/id/stations",
        "https://environment.data.gov.uk.evil.invalid/hydrology/id/stations",
        "https://user@environment.data.gov.uk/hydrology/id/stations",
        "https://environment.data.gov.uk:8443/hydrology/id/stations",
        "https://environment.data.gov.uk/hydrology/id/stations/../../secret",
    ],
)
def test_disallowed_targets(url: str) -> None:
    with pytest.raises(HydrologyError):
        check_url(url)


def test_url_scope_and_no_generic_fetch_target() -> None:
    url = request_url("observations", 0)
    check_url(url)
    assert httpx.URL(url).params.get_list("observedProperty") == ["waterLevel", "waterFlow"]
    assert "latest" in httpx.URL(url).params
    with pytest.raises(HydrologyError):
        request_url("https://evil.invalid", 0)


@pytest.mark.parametrize(
    "status,headers",
    [(302, {"location": "https://evil.invalid"}), (200, {"content-type": "text/html"})],
)
def test_redirect_and_content_type_rejected(
    tmp_path: Path, status: int, headers: dict[str, str]
) -> None:
    with pytest.raises(HydrologyError):
        fetch_snapshot(
            tmp_path,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, headers=headers, content=b"{}")
            ),
        )


def test_bounded_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("watergeo.ingestion.hydrology_client.time.sleep", lambda _: None)
    attempts = 0

    def retry(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return responder(request)

    fetch_snapshot(tmp_path, transport=httpx.MockTransport(retry))
    assert attempts == 8
    attempts = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic", request=request)

    with pytest.raises(HydrologyError):
        fetch_snapshot(tmp_path, transport=httpx.MockTransport(timeout))
    assert attempts == 3


def test_page_loop_and_incomplete_manifest(tmp_path: Path) -> None:
    def loop(request: httpx.Request) -> httpx.Response:
        response = responder(request)
        body = response.json()
        body["items"] = records()["stations"][:2]
        return httpx.Response(200, json=body)

    with pytest.raises(HydrologyError):
        fetch_snapshot(tmp_path, transport=httpx.MockTransport(loop))
    path = fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["pages"].pop()
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(HydrologyError):
        read_snapshot(path)


def test_json_duplicate_members_and_nonfinite_rejected() -> None:
    for body in [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"]:
        with pytest.raises(HydrologyError):
            decode(body)


@pytest.mark.parametrize(
    "query",
    [
        "lon=nan&lat=52",
        "lon=0&lat=91",
        "lon=0&lat=52&radius_m=100001",
        "lon=0&lat=52&limit=101",
        "lon=0&lat=52&radius_m=0",
        "lon=0&lat=52&url=https://evil.invalid",
    ],
)
def test_api_rejects_invalid_near_input(query: str) -> None:
    with TestClient(
        create_app(Settings(_env_file=None, db_password=SecretStr("synthetic-password")))
    ) as client:
        assert client.get("/v1/hydrology/stations/near?" + query).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("unitName", ""),
        ("unitName", "unknown"),
        ("period", True),
        ("parameter", "rainfall"),
        ("notation", "wrong"),
        ("unit", None),
    ],
)
def test_invalid_measure_contract(field: str, value: Any) -> None:
    raw = records()
    raw["measures"][0][field] = value
    with pytest.raises(HydrologyError):
        normalize(raw)


def test_missing_measure_is_not_silently_dropped() -> None:
    raw = records()
    raw["measures"].pop()
    raw["observations"].pop()
    with pytest.raises(HydrologyError, match="references"):
        normalize(raw)


def test_response_budget_and_metadata_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("watergeo.ingestion.hydrology_client.MAX_BYTES", 10)
    with pytest.raises(HydrologyError, match="budget"):
        fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    assert not list(tmp_path.glob("*/manifest.json"))


@pytest.mark.parametrize(
    "field,value", [("license", "unknown"), ("version", "future"), ("limit", 0), ("offset", 5)]
)
def test_changed_provenance_or_pagination_rejected(tmp_path: Path, field: str, value: Any) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        body = responder(request).json()
        body["meta"][field] = value
        return httpx.Response(200, json=body)

    with pytest.raises(HydrologyError):
        fetch_snapshot(tmp_path, transport=httpx.MockTransport(response))


@pytest.mark.parametrize(
    "raw",
    ["2020-01-01T00:00:00+00:99", "2020-01-01T00:00:00.1234567Z", "0001-01-01T00:00:00+01:00"],
)
def test_invalid_offset_precision_or_utc_overflow(raw: str) -> None:
    with pytest.raises(HydrologyError):
        timestamp(raw)
