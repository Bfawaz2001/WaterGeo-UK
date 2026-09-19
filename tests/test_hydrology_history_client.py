"""Bounded historical Hydrology API evidence client tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2 as httpx
import pytest

from watergeo.ingestion.hydrology import LICENCE, HydrologyError
from watergeo.ingestion.hydrology_history_client import (
    PAGE_LIMIT,
    fetch_history,
    read_history,
    request_url,
    validate_window,
)

MEASURE_ID = "abc-level-i-900-m-qualified"
MEASURE_URI = "http://environment.data.gov.uk/hydrology/id/measures/" + MEASURE_ID

START = datetime(2026, 9, 19, 0, 0, tzinfo=UTC)
END = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)


def response_items(
    offset: int,
    items: list[dict],
    *,
    limit: int = PAGE_LIMIT,
) -> httpx.Response:
    meta = {
        "publisher": "Environment Agency",
        "license": LICENCE,
        "licenseName": "OGL 3",
        "version": "2.1.1",
        "limit": limit,
    }

    if offset:
        meta["offset"] = offset

    return httpx.Response(
        200,
        json={
            "meta": meta,
            "items": items,
        },
        headers={"content-type": "application/json"},
    )


def reading(
    timestamp: str,
    *,
    value: float | None = 1.0,
    quality: str = "Unchecked",
) -> dict:
    result = {
        "measure": {"@id": MEASURE_URI},
        "date": timestamp[:10],
        "dateTime": timestamp,
        "quality": quality,
    }

    if value is not None:
        result["value"] = value

    return result


def test_window_requires_aware_times() -> None:
    with pytest.raises(HydrologyError, match="timezone-aware"):
        validate_window(
            datetime(2026, 9, 19),
            END,
        )


def test_window_rejects_more_than_31_days() -> None:
    with pytest.raises(HydrologyError, match="exceeds 31 days"):
        validate_window(
            START,
            START + timedelta(days=31, seconds=1),
        )


def test_request_url_is_bounded_and_deterministic() -> None:
    url = request_url(MEASURE_ID, START, END, 0)

    assert "mineq-dateTime=2026-09-19T00%3A00%3A00Z" in url
    assert "maxeq-dateTime=2026-09-19T01%3A00%3A00Z" in url
    assert f"_limit={PAGE_LIMIT}" in url
    assert "_sort=dateTime" in url
    assert "_offset=0" in url


def test_fetch_and_read_history(tmp_path: Path) -> None:
    rows = [
        reading("2026-09-19T00:00:00", value=0),
        reading(
            "2026-09-19T00:15:00",
            value=None,
            quality="Missing",
        ),
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "environment.data.gov.uk"
        assert request.url.path.endswith(f"/id/measures/{MEASURE_ID}/readings")

        return response_items(0, rows)

    directory = fetch_history(
        MEASURE_ID,
        START,
        END,
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    manifest, normalized = read_history(directory)

    assert manifest["measure_id"] == MEASURE_ID
    assert manifest["record_count"] == 2
    assert normalized.record_count == 2
    assert normalized.observations[0]["value"] == 0
    assert normalized.observations[1]["value"] is None


def test_duplicate_timestamp_fails_before_manifest(
    tmp_path: Path,
) -> None:
    row = reading("2026-09-19T00:00:00")

    def respond(request: httpx.Request) -> httpx.Response:
        return response_items(0, [row, row])

    with pytest.raises(
        HydrologyError,
        match="Duplicate historical observation timestamp",
    ):
        fetch_history(
            MEASURE_ID,
            START,
            END,
            root=tmp_path,
            transport=httpx.MockTransport(respond),
        )

    manifests = list(tmp_path.rglob("manifest.json"))
    assert manifests == []


def test_out_of_window_reading_fails_before_manifest(
    tmp_path: Path,
) -> None:
    row = reading("2026-09-20T00:00:00")

    def respond(request: httpx.Request) -> httpx.Response:
        return response_items(0, [row])

    with pytest.raises(
        HydrologyError,
        match="outside requested window",
    ):
        fetch_history(
            MEASURE_ID,
            START,
            END,
            root=tmp_path,
            transport=httpx.MockTransport(respond),
        )

    assert list(tmp_path.rglob("manifest.json")) == []


def test_redirect_is_rejected(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://environment.data.gov.uk/"},
        )

    with pytest.raises(
        HydrologyError,
        match="redirect",
    ):
        fetch_history(
            MEASURE_ID,
            START,
            END,
            root=tmp_path,
            transport=httpx.MockTransport(respond),
        )


def test_manifest_detects_raw_tampering(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return response_items(
            0,
            [reading("2026-09-19T00:00:00")],
        )

    directory = fetch_history(
        MEASURE_ID,
        START,
        END,
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    raw = directory / "readings-0.json"
    raw.write_bytes(raw.read_bytes() + b" ")

    with pytest.raises(
        HydrologyError,
        match="hash mismatch",
    ):
        read_history(directory)


def test_empty_history_is_valid(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return response_items(0, [])

    directory = fetch_history(
        MEASURE_ID,
        START,
        END,
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    manifest, normalized = read_history(directory)

    assert manifest["record_count"] == 0
    assert normalized.observations == []


def test_fetch_history_paginates_without_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import watergeo.ingestion.hydrology_history_client as history_client

    monkeypatch.setattr(history_client, "PAGE_LIMIT", 2)

    first_rows = [
        reading("2026-09-19T00:00:00", value=1),
        reading("2026-09-19T00:15:00", value=2),
    ]
    second_rows = [
        reading("2026-09-19T00:30:00", value=3),
    ]

    seen_offsets: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["_offset"])
        seen_offsets.append(offset)

        if offset == 0:
            return response_items(0, first_rows, limit=2)

        if offset == 2:
            return response_items(2, second_rows, limit=2)

        raise AssertionError(f"Unexpected offset: {offset}")

    directory = fetch_history(
        MEASURE_ID,
        START,
        END,
        root=tmp_path,
        transport=httpx.MockTransport(respond),
    )

    manifest, normalized = read_history(directory)

    assert seen_offsets == [0, 2]
    assert [page["offset"] for page in manifest["pages"]] == [0, 2]
    assert normalized.record_count == 3
    assert [row["observed_at"] for row in normalized.observations] == [
        "2026-09-19T00:00:00+00:00",
        "2026-09-19T00:15:00+00:00",
        "2026-09-19T00:30:00+00:00",
    ]
