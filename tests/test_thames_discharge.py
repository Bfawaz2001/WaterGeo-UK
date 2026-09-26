import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx2 as httpx
import pytest

from watergeo.db.thames_discharge_ingestion import load_snapshot
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


def body_bytes(body: dict[str, object]) -> bytes:
    return json.dumps(body, separators=(",", ":")).encode()


def transport(
    body: dict[str, object] | bytes | None = None, *, status: int = 200
) -> httpx.MockTransport:
    content = (
        body if isinstance(body, bytes) else body_bytes(body if body is not None else payload())
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            content=content,
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
    assert {path.name for path in directory.iterdir()} == {
        "manifest.json",
        "retrieval.json",
        "response.json",
    }
    assert json.loads((directory / "retrieval.json").read_bytes())["evidence_state"] == "retrieved"
    assert manifest["evidence_state"] == "validated"
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
    raw = body_bytes(payload(changed))
    with pytest.raises(ThamesDischargeError, match=message):
        client.fetch_snapshot(tmp_path, transport=transport(raw))
    (directory,) = list(tmp_path.iterdir())
    assert (directory / "response.json").read_bytes() == raw
    retrieval = json.loads((directory / "retrieval.json").read_bytes())
    assert retrieval["evidence_state"] == "retrieved"
    assert retrieval["response"]["bytes"] == len(raw)
    assert retrieval["response"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert not (directory / "manifest.json").exists()
    with pytest.raises(ThamesDischargeError):
        client.read_snapshot(directory)


def test_malformed_json_remains_exact_inspectable_unloadable_evidence(tmp_path: Path) -> None:
    raw = b'{"meta":{"publisher":"changed"},"items":['
    with pytest.raises(ThamesDischargeError, match="Malformed Thames Water JSON"):
        client.fetch_snapshot(tmp_path, transport=transport(raw))
    (directory,) = list(tmp_path.iterdir())
    assert (directory / "response.json").read_bytes() == raw
    assert (
        json.loads((directory / "retrieval.json").read_bytes())["content_sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    assert not (directory / "manifest.json").exists()
    engine = MagicMock()
    with pytest.raises(ThamesDischargeError):
        load_snapshot(engine, directory)
    engine.begin.assert_not_called()


@pytest.mark.parametrize(
    "corruption",
    ["body", "manifest", "retrieval", "unexpected_path", "declared_path", "symlink", "size"],
)
def test_read_rejects_changed_evidence(tmp_path: Path, corruption: str) -> None:
    directory = client.fetch_snapshot(tmp_path, transport=transport())
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if corruption == "body":
        (directory / "response.json").write_text("{}")
    elif corruption == "manifest":
        manifest["normalized_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
    elif corruption == "retrieval":
        retrieval_path = directory / "retrieval.json"
        retrieval = json.loads(retrieval_path.read_text())
        retrieval["content_sha256"] = "0" * 64
        retrieval_path.write_text(json.dumps(retrieval))
    elif corruption == "unexpected_path":
        (directory / "unexpected.json").write_text("{}")
    elif corruption == "declared_path":
        retrieval_path = directory / "retrieval.json"
        retrieval = json.loads(retrieval_path.read_text())
        manifest["response"]["file"] = "../response.json"
        retrieval["response"]["file"] = "../response.json"
        manifest_path.write_text(json.dumps(manifest))
        retrieval_path.write_text(json.dumps(retrieval))
    elif corruption == "symlink":
        response_path = directory / "response.json"
        outside = tmp_path / "outside.json"
        outside.write_bytes(response_path.read_bytes())
        response_path.unlink()
        response_path.symlink_to(outside)
    else:
        (directory / "response.json").write_bytes(b"x" * (client.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(ThamesDischargeError):
        client.read_snapshot(directory)


def test_fetch_rejects_redirect_and_retry_exhaustion(tmp_path: Path) -> None:
    with pytest.raises(ThamesDischargeError, match="redirect"):
        client.fetch_snapshot(tmp_path, transport=transport(status=302))
    with pytest.raises(ThamesDischargeError, match="temporarily"):
        client.fetch_snapshot(tmp_path, transport=transport(status=503))
