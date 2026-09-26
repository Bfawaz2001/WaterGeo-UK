"""Synthetic Thames Water publication, filtering and HTTP contracts."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_hydrology_http import engines as engines

from watergeo.api.app import create_app
from watergeo.db.thames_discharge_ingestion import load_snapshot
from watergeo.ingestion import thames_discharge_client as source
from watergeo.operations.refresh import RefreshRequest, refresh


def record(identity: str, status: str, x: int) -> dict[str, object]:
    return {
        "locationName": f"Site {identity}",
        "permitNumber": "CTCR.0001",
        "locationGridRef": "SU12345678",
        "x": x,
        "y": 156780,
        "receivingWaterCourse": "Synthetic Brook",
        "alertStatus": status,
        "statusChanged": "2026-09-20T12:30:00",
        "alertPast48Hours": status == "Discharging",
        "mostRecentDischargeAlertStart": "2026-09-20T12:00:00",
        "mostRecentDischargeAlertStop": None if status == "Discharging" else "2026-09-20T12:30:00",
        "uniqueId": identity,
    }


def transport() -> httpx.MockTransport:
    body = {
        "meta": {
            "publisher": "Thames Water Utilities Limited",
            "licence": "https://data.thameswater.co.uk/s/terms-of-service",
            "documentation": "https://docs.api.thameswater.co.uk/",
            "version": "2.0.1",
            "comment": "",
            "limit": "1000",
        },
        "items": [record("TWL00001", "Discharging", 412340), record("TWL00002", "Offline", 512340)],
    }
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200, json=body, headers={"content-type": "application/json"}, request=request
        )
    )


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    return source.fetch_snapshot(tmp_path, transport=transport())


@pytest.fixture
def loaded(engines, bundle: Path) -> Iterator[dict[str, Any]]:
    result = load_snapshot(engines[0], bundle)
    yield result
    with engines[2].begin() as connection:
        connection.execute(
            text("DELETE FROM watergeo.thames_discharge_site WHERE snapshot_id=:id"),
            {"id": result["snapshot_id"]},
        )
        connection.execute(
            text("DELETE FROM watergeo.thames_discharge_snapshot WHERE id=:id"),
            {"id": result["snapshot_id"]},
        )


def test_publication_api_filters_and_refresh(engines, bundle: Path, loaded: dict[str, Any]) -> None:
    assert loaded["status"] == "inserted"
    assert load_snapshot(engines[0], bundle) == {**loaded, "status": "existing"}
    with TestClient(create_app()) as api:
        prefix = "/v1/thames-water/discharge-status"
        dataset = api.get(prefix + "/dataset").json()
        assert dataset["site_count"] == 2
        assert dataset["discharging_count"] == dataset["offline_count"] == 1
        params = {"snapshot_id": dataset["snapshot_id"]}
        page = api.get(prefix + "/sites", params={**params, "limit": 1}).json()
        assert page["items"][0]["site_id"] == "TWL00001" and page["next_after_id"]
        filtered = api.get(prefix + "/sites", params={**params, "alert_status": "Offline"}).json()
        assert [row["site_id"] for row in filtered["items"]] == ["TWL00002"]
        recent = api.get(prefix + "/sites", params={**params, "alert_past_48_hours": True}).json()
        assert [row["site_id"] for row in recent["items"]] == ["TWL00001"]
        detail = api.get(prefix + "/sites/TWL00001", params=params)
        assert detail.status_code == 200 and detail.json()["alert_status"] == "Discharging"
        near = api.get(
            prefix + "/sites/near",
            params={**params, "lon": -1.82, "lat": 51.31, "radius_m": 200000},
        ).json()
        assert near["items"] and near["items"][0]["distance_m"] is not None
        assert api.get(prefix + "/sites/TWL99999", params=params).status_code == 404
        assert api.get(prefix + "/sites?alert_status=unsafe").status_code == 422
    result = refresh(engines[0], RefreshRequest("thames-discharge-status", bundle), "synthetic")
    assert result == {"status": "existing", "snapshot_id": loaded["snapshot_id"]}
