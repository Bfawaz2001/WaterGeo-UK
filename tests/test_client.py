"""Deterministic SDK tests; no network or database access."""

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import httpx2 as httpx
import pytest

from watergeo.client import (
    WaterGeoAPIError,
    WaterGeoClient,
    WaterGeoConfigurationError,
    WaterGeoResponseError,
    WaterGeoTransportError,
)

SNAPSHOT = "00000000-0000-4000-8000-000000000001"


def client(responder: Any, **kwargs: Any) -> WaterGeoClient:
    return WaterGeoClient(
        "http://watergeo.test/root/", transport=httpx.MockTransport(responder), **kwargs
    )


def hydrology_dataset() -> dict[str, Any]:
    return {
        "snapshot_id": SNAPSHOT,
        "publisher": "Environment Agency",
        "source_api": "https://example.test",
        "documentation_url": "https://example.test/docs",
        "licence": "Open Government Licence v3",
        "licence_url": "https://example.test/licence",
        "attribution": "Contains public information",
        "geographic_coverage": "England",
        "scope": ["waterLevel"],
        "content_sha256": "a" * 64,
        "normalization_version": "test-v1",
        "retrieval_started_at": "2026-01-01T00:00:00Z",
        "retrieval_completed_at": "2026-01-01T00:01:00Z",
        "station_count": 2,
        "station_with_location_count": 2,
        "station_without_location_count": 0,
        "measure_count": 0,
        "latest_observation_count": 0,
        "freshness_caveat": "Test snapshot",
        "request_manifest": {},
    }


def station_page(ids: list[str], next_cursor: str | None) -> dict[str, Any]:
    return {
        "dataset": hydrology_dataset(),
        "items": [
            {
                "station_id": station_id,
                "source_uri": f"https://example.test/{station_id}",
                "labels": [station_id],
                "location_status": "available",
                "latitude": 52.0,
                "longitude": -2.0,
                "geometry": {"type": "Point", "coordinates": [-2.0, 52.0]},
            }
            for station_id in ids
        ],
        "next_after_id": next_cursor,
    }


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.test",
        "https://user:secret@example.test",
        "https://example.test?token=secret",
        "https://example.test/#fragment",
    ],
)
def test_base_url_rejects_unsafe_or_ambiguous_values(url: str) -> None:
    with pytest.raises(WaterGeoConfigurationError):
        WaterGeoClient(url)


def test_base_path_and_trailing_slash_are_normalized() -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    with client(responder) as api:
        assert api.health().status == "ok"
    assert requests[0].url == "http://watergeo.test/root/health"
    assert requests[0].headers["accept"] == "application/json, application/geo+json"


def test_redirect_is_not_followed() -> None:
    with (
        client(
            lambda _: httpx.Response(302, headers={"location": "https://other.test/secret"})
        ) as api,
        pytest.raises(WaterGeoAPIError) as caught,
    ):
        api.health()
    assert caught.value.status_code == 302
    assert caught.value.detail == "Unexpected redirect"


def test_transport_failure_is_stable_and_sanitized() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("credential=private", request=request)

    with (
        client(responder) as api,
        pytest.raises(WaterGeoTransportError, match="WaterGeo request failed") as caught,
    ):
        api.health()
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("status", [404, 422, 503])
def test_api_errors_preserve_status_and_bounded_detail(status: int) -> None:
    with (
        client(lambda _: httpx.Response(status, json={"detail": "x" * 5000})) as api,
        pytest.raises(WaterGeoAPIError) as caught,
    ):
        api.health()
    assert caught.value.status_code == status
    assert caught.value.detail == "x" * 4096


def test_non_json_error_body_is_not_exposed() -> None:
    with (
        client(lambda _: httpx.Response(500, text="private database details")) as api,
        pytest.raises(WaterGeoAPIError) as caught,
    ):
        api.health()
    assert caught.value.detail == "Request failed"
    assert "private database" not in str(caught.value)


def test_unexpected_content_type_and_invalid_schema_are_rejected() -> None:
    with (
        client(
            lambda _: httpx.Response(200, text="ok", headers={"content-type": "text/plain"})
        ) as api,
        pytest.raises(WaterGeoResponseError, match="content type"),
    ):
        api.health()
    with (
        client(lambda _: httpx.Response(200, json={"status": "wrong"})) as api,
        pytest.raises(WaterGeoResponseError, match="contract"),
    ):
        api.health()


def test_response_size_is_bounded_while_streaming() -> None:
    with (
        client(lambda _: httpx.Response(200, content=b"x" * 1025), max_response_bytes=1024) as api,
        pytest.raises(WaterGeoResponseError, match="size limit"),
    ):
        api.health()


def test_station_iterator_pins_first_snapshot_and_advances_cursor() -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=station_page(["A"], "A"))
        return httpx.Response(200, json=station_page(["B"], None))

    with client(responder) as api:
        stations = list(api.iter_hydrology_stations(page_size=1))
    assert [station.station_id for station in stations] == ["A", "B"]
    assert requests[0].url.params.get("snapshot_id") is None
    assert requests[1].url.params["snapshot_id"] == SNAPSHOT
    assert requests[1].url.params["after_id"] == "A"


@pytest.mark.parametrize("snapshot_id", [None, UUID(SNAPSHOT)])
def test_station_iterator_rejects_changed_snapshot(snapshot_id: UUID | None) -> None:
    calls = 0

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = station_page(["A"], "A" if calls == 1 else None)
        if calls == 2:
            body["dataset"]["snapshot_id"] = "00000000-0000-4000-8000-000000000002"
        return httpx.Response(200, json=body)

    with (
        client(responder) as api,
        pytest.raises(WaterGeoResponseError, match="changed snapshot"),
    ):
        list(api.iter_hydrology_stations(page_size=1, snapshot_id=snapshot_id))


@pytest.mark.parametrize(
    "iterator_name,fetch_name,positional,next_field,next_cursor",
    [
        ("iter_hydrology_stations", "hydrology_stations", (), "next_after_id", "A"),
        (
            "iter_management_catchments",
            "management_catchments",
            (),
            "next_after_id",
            "A",
        ),
        (
            "iter_water_quality_sampling_points",
            "water_quality_sampling_points",
            (),
            "next_after_id",
            "A",
        ),
        ("iter_reservoirs", "reservoirs", (), "next_after_id", "A"),
        (
            "iter_reservoir_readings",
            "reservoir_readings",
            ("1",),
            "next_after",
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ],
)
def test_supplied_snapshot_is_used_and_remains_pinned(
    iterator_name: str,
    fetch_name: str,
    positional: tuple[str, ...],
    next_field: str,
    next_cursor: str | datetime,
) -> None:
    selected = UUID(SNAPSHOT)
    page_one = SimpleNamespace(
        dataset=SimpleNamespace(snapshot_id=selected),
        items=["one"],
        **{next_field: next_cursor},
    )
    page_two = SimpleNamespace(
        dataset=SimpleNamespace(snapshot_id=selected),
        items=["two"],
        **{next_field: None},
    )
    api = client(lambda _: pytest.fail("iterator fetch method must be mocked"))
    fetch = MagicMock(side_effect=[page_one, page_two])
    setattr(api, fetch_name, fetch)

    results = list(getattr(api, iterator_name)(*positional, page_size=1, snapshot_id=selected))

    assert results == ["one", "two"]
    assert fetch.call_args_list[0].kwargs["snapshot_id"] == selected
    assert fetch.call_args_list[1].kwargs["snapshot_id"] == selected
    api.close()


def test_supplied_snapshot_rejects_first_mismatched_page() -> None:
    requested = UUID(SNAPSHOT)
    returned = "00000000-0000-4000-8000-000000000002"

    def responder(request: httpx.Request) -> httpx.Response:
        body = station_page(["A"], None)
        body["dataset"]["snapshot_id"] = returned
        return httpx.Response(200, json=body)

    with (
        client(responder) as api,
        pytest.raises(WaterGeoResponseError, match="changed snapshot"),
    ):
        list(api.iter_hydrology_stations(snapshot_id=requested))


def test_iterator_rejects_repeated_cursor_and_enforces_bounds() -> None:
    def repeated(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=station_page(["A"], "A"))

    with client(repeated) as api, pytest.raises(WaterGeoResponseError, match="repeated"):
        list(api.iter_hydrology_stations(page_size=1))

    def pages() -> Iterator[tuple[list[int], int | None]]:
        yield [1, 2], 2
        yield [3], None

    values = pages()
    with pytest.raises(WaterGeoResponseError, match="record limit"):
        list(
            WaterGeoClient._iterate(
                lambda: next(values), lambda _: next(values), max_pages=2, max_records=2
            )
        )


def test_opaque_path_identifier_is_percent_encoded() -> None:
    request_path = ""

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal request_path
        request_path = request.url.raw_path.decode()
        return httpx.Response(404, json={"detail": "Sampling point not found"})

    with client(responder) as api, pytest.raises(WaterGeoAPIError):
        api.water_quality_sampling_point("AN/CORBY space", snapshot_id=UUID(SNAPSHOT))
    assert request_path.endswith("/AN%2FCORBY%20space?snapshot_id=" + SNAPSHOT)


def test_manual_page_method_remains_available() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "1"
        assert request.url.params["after_id"] == "A"
        assert request.url.params["snapshot_id"] == SNAPSHOT
        return httpx.Response(200, json=station_page(["B"], None))

    with client(responder) as api:
        page = api.hydrology_stations(limit=1, after_id="A", snapshot_id=UUID(SNAPSHOT))
    assert page.items[0].station_id == "B"


def test_public_methods_cover_every_openapi_route() -> None:
    api = client(lambda _: pytest.fail("mocked _get must prevent HTTP"))
    api._get = MagicMock(return_value=object())  # type: ignore[method-assign]
    retrieval_id = UUID(SNAPSHOT)
    cursor = datetime(2026, 1, 1, tzinfo=UTC)

    api.health()
    api.readiness()
    api.source_status()
    api.water_supply_dataset()
    api.water_supply_areas()
    api.water_supply_areas_at_point(-2, 52)
    api.water_supply_area(1)
    api.water_supply_geometry(1)
    api.hydrology_dataset()
    api.hydrology_stations()
    api.hydrology_stations_near(-2, 52)
    api.hydrology_station("station")
    api.hydrology_history(retrieval_id, after=cursor)
    api.catchment_dataset()
    api.river_basin_districts()
    api.river_basin_district("1")
    api.management_catchments()
    api.management_catchment("2")
    api.operational_catchments()
    api.operational_catchment("3")
    api.water_bodies()
    api.water_body("GB123")
    api.water_body_geometry("GB123")
    api.water_quality_dataset()
    api.water_quality_sampling_points()
    api.water_quality_sampling_points_near(-2, 52)
    api.water_quality_sampling_point("AN/CORBY")
    api.water_quality_observations(retrieval_id)
    api.reservoir_level_dataset()
    api.reservoirs()
    api.reservoirs_near(-2, 52)
    api.reservoir("1")
    api.reservoir_readings("1", after=cursor)

    paths = {call.args[0] for call in api._get.call_args_list}  # type: ignore[attr-defined]
    assert paths == {
        "health",
        "ready",
        "v1/sources/status",
        "v1/water-supply/dataset",
        "v1/water-supply/areas",
        "v1/water-supply/areas/at-point",
        "v1/water-supply/areas/1",
        "v1/water-supply/areas/1/geometry",
        "v1/hydrology/dataset",
        "v1/hydrology/stations",
        "v1/hydrology/stations/near",
        "v1/hydrology/stations/station",
        f"v1/hydrology/history/{retrieval_id}",
        "v1/catchments/dataset",
        "v1/catchments/river-basin-districts",
        "v1/catchments/river-basin-districts/1",
        "v1/catchments/management-catchments",
        "v1/catchments/management-catchments/2",
        "v1/catchments/operational-catchments",
        "v1/catchments/operational-catchments/3",
        "v1/catchments/water-bodies",
        "v1/catchments/water-bodies/GB123",
        "v1/catchments/water-bodies/GB123/geometry",
        "v1/water-quality/dataset",
        "v1/water-quality/sampling-points",
        "v1/water-quality/sampling-points/near",
        "v1/water-quality/sampling-points/AN%2FCORBY",
        f"v1/water-quality/observations/{retrieval_id}",
        "v1/severn-trent/reservoir-levels/dataset",
        "v1/severn-trent/reservoir-levels/reservoirs",
        "v1/severn-trent/reservoir-levels/reservoirs/near",
        "v1/severn-trent/reservoir-levels/reservoirs/1",
        "v1/severn-trent/reservoir-levels/reservoirs/1/readings",
    }
    api.close()
