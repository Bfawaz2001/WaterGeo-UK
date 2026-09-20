import json
from pathlib import Path

import httpx2 as httpx
import pytest

from watergeo.ingestion.catchment_client import (
    RequestPacer,
    _request,
    _source_url,
    read_snapshot,
)
from watergeo.ingestion.catchments import CatchmentError


def test_source_url_accepts_only_reviewed_cycle3_targets() -> None:
    _source_url("https://environment.data.gov.uk/catchment-planning/v/c3-plan")
    _source_url(
        "https://environment.data.gov.uk/catchment-planning/v/c3-plan/OperationalCatchment/3471"
    )
    _source_url(
        "https://environment.data.gov.uk/catchment-planning/v/c3-plan/RiverBasinDistrict/4.geojson"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://environment.data.gov.uk/catchment-planning/v/c3-plan",
        "https://example.com/catchment-planning/v/c3-plan",
        ("https://environment.data.gov.uk/catchment-planning/OperationalCatchment/3471"),
        (
            "https://environment.data.gov.uk/"
            "catchment-planning/v/c3-plan/OperationalCatchment/3471/print"
        ),
        (
            "https://environment.data.gov.uk/"
            "catchment-planning/v/c3-plan/OperationalCatchment/3471?x=1"
        ),
    ],
)
def test_source_url_rejects_unreviewed_targets(url: str) -> None:
    with pytest.raises(CatchmentError):
        _source_url(url)


def test_request_pacer_enforces_interval() -> None:
    state = {"now": 100.0}
    sleeps: list[float] = []

    def clock() -> float:
        return state["now"]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        state["now"] += seconds

    pacer = RequestPacer(
        6.0,
        clock=clock,
        sleeper=sleeper,
    )

    pacer.wait()
    state["now"] += 2.0
    pacer.wait()

    assert sleeps == [4.0]


def test_request_rejects_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://example.com/"},
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        httpx.Client(
            transport=transport,
            trust_env=False,
        ) as client,
        pytest.raises(
            CatchmentError,
            match="redirect",
        ),
    ):
        _request(
            client,
            ("https://environment.data.gov.uk/catchment-planning/v/c3-plan"),
            expected="html",
            pacer=RequestPacer(0),
        )


def test_request_fails_closed_after_repeated_403() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            403,
            headers={"content-type": "text/html"},
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        httpx.Client(
            transport=transport,
            trust_env=False,
        ) as client,
        pytest.raises(
            CatchmentError,
            match="temporarily unavailable",
        ),
    ):
        _request(
            client,
            ("https://environment.data.gov.uk/catchment-planning/v/c3-plan"),
            expected="html",
            pacer=RequestPacer(0),
        )

    assert attempts == 3


def test_request_rejects_wrong_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"{}",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        httpx.Client(
            transport=transport,
            trust_env=False,
        ) as client,
        pytest.raises(
            CatchmentError,
            match="HTML content type",
        ),
    ):
        _request(
            client,
            ("https://environment.data.gov.uk/catchment-planning/v/c3-plan"),
            expected="html",
            pacer=RequestPacer(0),
        )


def test_read_snapshot_requires_completion_manifest(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "incomplete"
    directory.mkdir()

    (directory / "root.html").write_text("<html></html>")

    with pytest.raises(
        CatchmentError,
        match="manifest",
    ):
        read_snapshot(directory)


def test_read_snapshot_rejects_wrong_source(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "bad"
    directory.mkdir()

    manifest = {
        "source": "https://example.com/",
        "plan_version": "c3-plan",
        "normalization_version": "ea-cde-c3-plan-v1",
        "retrieval_started_at": "2026-09-19T00:00:00+00:00",
        "retrieval_completed_at": "2026-09-19T00:01:00+00:00",
        "entries": [],
    }

    (directory / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(
        CatchmentError,
        match="Unsupported catchment evidence bundle",
    ):
        read_snapshot(directory)


def test_live_reviewed_response_budgets_are_large_enough() -> None:
    from watergeo.ingestion.catchment_client import (
        MAX_HTML_BYTES,
        MAX_TOTAL_BYTES,
    )

    # Reviewed 2026-09-19 Cycle 3 responses:
    # root HTML = 19,212,139 bytes
    # Humber RBD HTML = 4,804,522 bytes
    assert MAX_HTML_BYTES >= 19_212_139
    assert MAX_TOTAL_BYTES >= 512 * 1024 * 1024
