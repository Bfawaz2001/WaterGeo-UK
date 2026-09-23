import json
from pathlib import Path

import httpx2 as httpx
import pytest

from watergeo.ingestion import stream_reservoir_client as client
from watergeo.ingestion.stream_reservoirs import (
    ITEM_ID,
    ITEM_TITLE,
    LAYER_NAME,
    SERVICE_ROOT,
    StreamReservoirError,
)


def item(*, modified=1779030284000):
    return {
        "id": ITEM_ID,
        "title": ITEM_TITLE,
        "type": "Feature Service",
        "access": "public",
        "accessInformation": "Severn Trent Water",
        "url": SERVICE_ROOT,
        "created": 1779029424000,
        "modified": modified,
        "licenseInfo": "Licensed under CC BY 4.0",
    }


def layer():
    types = {
        "RESERVOIR_ID": "esriFieldTypeString",
        "RESERVOIR_NAME": "esriFieldTypeString",
        "DATE": "esriFieldTypeDate",
        "LATITUDE": "esriFieldTypeString",
        "LONGITUDE": "esriFieldTypeString",
        "CAPACITY": "esriFieldTypeString",
        "CAPACITY_UNITS": "esriFieldTypeString",
        "CURRENT_LEVEL": "esriFieldTypeString",
        "CURRENT_LEVEL_UNITS": "esriFieldTypeString",
        "CURRENT_PERCENTAGE": "esriFieldTypeDouble",
        "FID": "esriFieldTypeOID",
    }
    return {
        "id": 0,
        "name": LAYER_NAME,
        "type": "Feature Layer",
        "geometryType": "esriGeometryPoint",
        "objectIdField": "FID",
        "capabilities": "Query",
        "maxRecordCount": 2000,
        "extent": {"spatialReference": {"wkid": 102100, "latestWkid": 3857}},
        "dateFieldsTimeReference": {
            "timeZone": "UTC",
            "timeZoneIANA": "Etc/UTC",
            "respectsDaylightSaving": False,
        },
        "fields": [{"name": name, "type": kind} for name, kind in types.items()],
    }


def feature(identity, reservoir="10014", observed=1736121600000, percentage=90.2):
    properties = {
        "RESERVOIR_ID": reservoir,
        "RESERVOIR_NAME": "DRAYCOTE RES" if reservoir == "10014" else "OTHER RES",
        "DATE": observed,
        "LATITUDE": "52.31929693",
        "LONGITUDE": "-1.318895597",
        "CAPACITY": "23000",
        "CAPACITY_UNITS": "ML",
        "CURRENT_LEVEL": "20746",
        "CURRENT_LEVEL_UNITS": "ML",
        "CURRENT_PERCENTAGE": percentage,
        "FID": identity,
    }
    return {
        "type": "Feature",
        "id": identity,
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [-1.318895597, 52.31929693]},
    }


def transport(*, changed_ids=False, changed_item=False, redirect=False):
    id_calls = 0
    item_calls = 0

    def respond(request):
        nonlocal id_calls, item_calls
        if redirect:
            return httpx.Response(302, headers={"location": "https://example.com"})
        path = request.url.path
        query = dict(request.url.params)
        if path.endswith(ITEM_ID):
            item_calls += 1
            body = item(
                modified=1779030284001 if changed_item and item_calls == 2 else 1779030284000
            )
        elif path.endswith("/FeatureServer/0"):
            body = layer()
        elif query.get("returnIdsOnly") == "true":
            id_calls += 1
            values = [1, 2, 3] if changed_ids and id_calls == 2 else [1, 2]
            body = {"objectIdFieldName": "FID", "objectIds": values}
        else:
            body = {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                "features": [
                    feature(1),
                    feature(2, reservoir="10015", observed=1736726400000, percentage=80.0),
                ],
            }
        return httpx.Response(
            200,
            json=body,
            headers={"content-type": "application/json", "etag": "reviewed"},
            request=request,
        )

    return httpx.MockTransport(respond)


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _: None)


def test_fetch_read_round_trip_and_deterministic_normalization(tmp_path: Path):
    directory = client.fetch_snapshot(tmp_path, transport=transport())
    manifest, data = client.read_snapshot(directory)
    assert manifest["reservoir_count"] == 2
    assert manifest["reading_count"] == 2
    assert [row["reservoir_id"] for row in data.reservoirs] == ["10014", "10015"]
    assert data.readings[0]["observed_at"] == "2025-01-06T00:00:00+00:00"
    assert data.readings[0]["current_level"] == 20746
    assert len(manifest["entries"]) == 6


@pytest.mark.parametrize("change", ["ids", "item"])
def test_fetch_rejects_source_change_during_retrieval(tmp_path: Path, change: str):
    with pytest.raises(StreamReservoirError, match="changed"):
        client.fetch_snapshot(
            tmp_path,
            transport=transport(changed_ids=change == "ids", changed_item=change == "item"),
        )


def test_fetch_rejects_redirect(tmp_path: Path):
    with pytest.raises(StreamReservoirError, match="redirect"):
        client.fetch_snapshot(tmp_path, transport=transport(redirect=True))


@pytest.mark.parametrize(
    ("part", "value", "message"),
    [
        ("properties", {"CURRENT_PERCENTAGE": float("nan")}, "Malformed"),
        ("properties", {"CURRENT_LEVEL_UNITS": "m"}, "quantity"),
        ("properties", {"RESERVOIR_ID": "bad id"}, "identity"),
        ("properties", {"DATE": 1767225600000}, "date"),
        ("geometry", {"coordinates": [0, 0]}, "disagree"),
    ],
)
def test_normalization_rejects_unreviewed_values(
    tmp_path: Path, part: str, value: dict, message: str
):
    base = transport()

    def respond(request):
        response = base.handle_request(request)
        if request.url.params.get("f") == "geojson":
            payload = json.loads(response.content)
            if part == "properties":
                payload["features"][0]["properties"].update(value)
            else:
                payload["features"][0]["geometry"].update(value)
            return httpx.Response(
                200,
                content=json.dumps(payload, allow_nan=True),
                headers={"content-type": "application/json"},
                request=request,
            )
        return response

    with pytest.raises(StreamReservoirError, match=message):
        client.fetch_snapshot(tmp_path, transport=httpx.MockTransport(respond))


@pytest.mark.parametrize("corruption", ["body", "manifest", "path", "header"])
def test_read_rejects_changed_evidence(tmp_path: Path, corruption: str):
    directory = client.fetch_snapshot(tmp_path, transport=transport())
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if corruption == "body":
        (directory / "response-003.json").write_bytes(b"{}")
    elif corruption == "manifest":
        manifest["normalized_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
    elif corruption == "path":
        (directory / "unexpected.json").write_text("{}")
    else:
        manifest["entries"][3]["headers"] = {}
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(StreamReservoirError):
        client.read_snapshot(directory)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.arcgis.com/sharing/rest/content/items/0bbd0dd0487346a893d4d615aad9d289?f=json",
        "https://example.com/query?f=geojson",
        client.LAYER_URL + "/query?where=1%3D1&f=geojson",
    ],
)
def test_request_target_is_fixed(url: str):
    with pytest.raises(StreamReservoirError):
        client._allowed_url(url)


def test_real_review_budgets_fit_contract():
    assert client.MAX_RESPONSE_BYTES > 271_267
    assert client.PAGE_SIZE == 250
    assert client.MAX_PAGES * client.PAGE_SIZE >= 2000
