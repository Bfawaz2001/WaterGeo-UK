import json
from pathlib import Path

import httpx2 as httpx
import pytest

from watergeo.ingestion import thames_discharge_client as client
from watergeo.ingestion.thames_discharge import ThamesDischargeError


def item(identity: str = "TWL00001", status: str = "Not discharging") -> dict[str, object]:
    return {
        "locationName": "Synthetic works",
        "permitNumber": "CTCR.0001",
        "locationGridRef": "SU12345678",
        "x": 412340,
        "y": 156780,
        "receivingWaterCourse": "Synthetic Brook",
        "alertStatus": status,
        "statusChanged": "2026-09-20T12:30:00",
        "alertPast48Hours": status == "Discharging",
        "mostRecentDischargeAlertStart": "2026-09-20T12:00:00",
        "mostRecentDischargeAlertStop": None if status == "Discharging" else "2026-09-20T12:30:00",
        "uniqueId": identity,
    }


def payload(*items: dict[str, object]) -> dict[str, object]:
    return {
        "meta": {
            "publisher": "Thames Water Utilities Limited",
            "licence": "https://data.thameswater.co.uk/s/terms-of-service",
            "documentation": "https://docs.api.thameswater.co.uk/",
            "version": "2.0.1",
            "comment": "",
            "limit": "1000",
        },
        "items": list(items) or [item()],
    }


def transport(body: dict[str, object] | None = None, *, status: int = 200) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json=body or payload(),
            headers={"content-type": "application/json", "etag": "synthetic"},
            request=request,
        )

    return httpx.MockTransport(respond)


def test_fetch_read_round_trip_preserves_source_semantics(tmp_path: Path) -> None:
    directory = client.fetch_snapshot(
        tmp_path,
        transport=transport(payload(item("TWL00002", "Discharging"), item("TWL00001"))),
    )
    manifest, data = client.read_snapshot(directory)
    assert manifest["site_count"] == 2
    assert [row["site_id"] for row in data.sites] == ["TWL00001", "TWL00002"]
    assert data.sites[1]["most_recent_discharge_stop"] is None
    assert data.sites[1]["status_changed"] == "2026-09-20T12:30:00"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"uniqueId": "unsafe"}, "identity"),
        ({"alertStatus": "Unknown"}, "alert state"),
        ({"x": "NaN"}, "coordinate"),
        ({"statusChanged": "2026-09-20T12:30:00Z"}, "Invalid"),
        ({"extra": "field"}, "fields changed"),
    ],
)
def test_fetch_rejects_unreviewed_source_values(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    changed = item()
    changed.update(change)
    with pytest.raises(ThamesDischargeError, match=message):
        client.fetch_snapshot(tmp_path, transport=transport(payload(changed)))


@pytest.mark.parametrize("corruption", ["body", "manifest", "path"])
def test_read_rejects_changed_evidence(tmp_path: Path, corruption: str) -> None:
    directory = client.fetch_snapshot(tmp_path, transport=transport())
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if corruption == "body":
        (directory / "response.json").write_text("{}")
    elif corruption == "manifest":
        manifest["normalized_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
    else:
        (directory / "unexpected.json").write_text("{}")
    with pytest.raises(ThamesDischargeError):
        client.read_snapshot(directory)


def test_fetch_rejects_redirect_and_retry_exhaustion(tmp_path: Path) -> None:
    with pytest.raises(ThamesDischargeError, match="redirect"):
        client.fetch_snapshot(tmp_path, transport=transport(status=302))
    with pytest.raises(ThamesDischargeError, match="temporarily"):
        client.fetch_snapshot(tmp_path, transport=transport(status=503))
