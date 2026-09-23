"""Synchronous, typed HTTP client for public WaterGeo read routes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any, TypeVar
from urllib.parse import quote
from uuid import UUID

import httpx2 as httpx
from pydantic import BaseModel, ValidationError

from watergeo.client.errors import (
    WaterGeoAPIError,
    WaterGeoConfigurationError,
    WaterGeoResponseError,
    WaterGeoTransportError,
)
from watergeo.client.models import (
    AreaDetail,
    AreaFeature,
    AreaPage,
    AreaSummary,
    CatchmentDataset,
    Health,
    HistoricalObservation,
    HistoryRetrievalResponse,
    HydrologyDataset,
    ManagementCatchment,
    ManagementCatchmentDetail,
    ManagementCatchmentPage,
    OperationalCatchment,
    OperationalCatchmentDetail,
    OperationalCatchmentPage,
    Readiness,
    Reservoir,
    ReservoirDetail,
    ReservoirLevelDataset,
    ReservoirPage,
    ReservoirReading,
    ReservoirReadingPage,
    RiverBasinDistrict,
    RiverBasinDistrictDetail,
    RiverBasinDistrictPage,
    SamplingPoint,
    SamplingPointDetail,
    SamplingPointPage,
    SourceStatuses,
    Station,
    StationDetail,
    StationPage,
    WaterBody,
    WaterBodyDetail,
    WaterBodyGeometryCollection,
    WaterBodyPage,
    WaterQualityDataset,
    WaterQualityObservation,
    WaterQualityObservationRetrieval,
    WaterSupplyDataset,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
ItemT = TypeVar("ItemT")
CursorT = TypeVar("CursorT", str, int, datetime)

DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_PAGES = 1000
DEFAULT_MAX_RECORDS = 100_000
ERROR_DETAIL_BYTES = 4096


def _identifier(value: object) -> str:
    return quote(str(value), safe="")


def _params(**values: object) -> dict[str, str | int | float]:
    result: dict[str, str | int | float] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (UUID, datetime)):
            result[key] = value.isoformat() if isinstance(value, datetime) else str(value)
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            result[key] = value
        else:
            raise WaterGeoConfigurationError(f"Unsupported query value for {key}")
    return result


class WaterGeoClient:
    """A bounded synchronous client for one explicitly configured WaterGeo server."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float | httpx.Timeout = 30.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        try:
            url = httpx.URL(base_url)
        except (TypeError, ValueError) as error:
            raise WaterGeoConfigurationError("Invalid WaterGeo base URL") from error
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.fragment
            or url.query
        ):
            raise WaterGeoConfigurationError(
                "Base URL must be HTTP(S), without credentials, query parameters, or a fragment"
            )
        if type(max_response_bytes) is not int or max_response_bytes < 1024:
            raise WaterGeoConfigurationError("max_response_bytes must be at least 1024")
        normalized = str(url.copy_with(path=url.path.rstrip("/") + "/"))
        self._max_response_bytes = max_response_bytes
        self._http = httpx.Client(
            base_url=normalized,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
            follow_redirects=False,
            headers={"Accept": "application/json, application/geo+json"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> WaterGeoClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, model: type[ModelT], **params: object) -> ModelT:
        try:
            with self._http.stream("GET", path.lstrip("/"), params=_params(**params)) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise WaterGeoResponseError("Response exceeds configured size limit")
        except WaterGeoResponseError:
            raise
        except httpx.TransportError as error:
            raise WaterGeoTransportError("WaterGeo request failed") from error

        if 300 <= response.status_code < 400:
            raise WaterGeoAPIError(response.status_code, "Unexpected redirect")
        if not 200 <= response.status_code < 300:
            detail = "Request failed"
            try:
                value = response.json()
                if isinstance(value, dict) and isinstance(value.get("detail"), str):
                    detail = value["detail"][:ERROR_DETAIL_BYTES]
            except ValueError:
                pass
            raise WaterGeoAPIError(response.status_code, detail)
        media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if media_type not in {"application/json", "application/geo+json"}:
            raise WaterGeoResponseError("Unexpected response content type")
        try:
            return model.model_validate_json(bytes(body))
        except (ValidationError, ValueError) as error:
            raise WaterGeoResponseError("Response does not match the WaterGeo contract") from error

    @staticmethod
    def _iterate(
        first: Callable[[], tuple[list[ItemT], CursorT | None]],
        following: Callable[[CursorT], tuple[list[ItemT], CursorT | None]],
        *,
        max_pages: int,
        max_records: int,
    ) -> Iterator[ItemT]:
        if type(max_pages) is not int or type(max_records) is not int:
            raise WaterGeoConfigurationError("Pagination bounds must be integers")
        if max_pages < 1 or max_records < 1:
            raise WaterGeoConfigurationError("Pagination bounds must be positive")
        cursor: CursorT | None = None
        seen: set[CursorT] = set()
        count = 0
        for page_number in range(max_pages):
            items, next_cursor = first() if page_number == 0 else following(cursor)  # type: ignore[arg-type]
            for item in items:
                count += 1
                if count > max_records:
                    raise WaterGeoResponseError("Pagination record limit exceeded")
                yield item
            if next_cursor is None:
                return
            if next_cursor == cursor or next_cursor in seen:
                raise WaterGeoResponseError("Server returned a repeated pagination cursor")
            seen.add(next_cursor)
            cursor = next_cursor
        raise WaterGeoResponseError("Pagination page limit exceeded")

    @staticmethod
    def _verify_snapshot(expected: list[UUID | None], actual: UUID) -> None:
        if expected[0] is None:
            expected[0] = actual
        elif actual != expected[0]:
            raise WaterGeoResponseError("Server changed snapshot during pagination")

    def health(self) -> Health:
        return self._get("health", Health)

    def readiness(self) -> Readiness:
        return self._get("ready", Readiness)

    def source_status(self) -> SourceStatuses:
        return self._get("v1/sources/status", SourceStatuses)

    def water_supply_dataset(self) -> WaterSupplyDataset:
        return self._get("v1/water-supply/dataset", WaterSupplyDataset)

    def water_supply_areas(self, *, limit: int = 50, after_id: int = 0) -> AreaPage:
        return self._get("v1/water-supply/areas", AreaPage, limit=limit, after_id=after_id)

    def iter_water_supply_areas(
        self,
        *,
        page_size: int = 100,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[AreaSummary]:
        snapshot: list[UUID | None] = [None]

        def page(cursor: int) -> tuple[list[AreaSummary], int | None]:
            result = self.water_supply_areas(limit=page_size, after_id=cursor)
            self._verify_snapshot(snapshot, result.snapshot_id)
            return result.items, result.next_after_id

        return self._iterate(
            lambda: page(0),
            page,
            max_pages=max_pages,
            max_records=max_records,
        )

    def water_supply_areas_at_point(
        self, lon: float, lat: float, *, limit: int = 50, after_id: int = 0
    ) -> AreaPage:
        return self._get(
            "v1/water-supply/areas/at-point",
            AreaPage,
            lon=lon,
            lat=lat,
            limit=limit,
            after_id=after_id,
        )

    def water_supply_area(self, source_id: int) -> AreaDetail:
        return self._get(f"v1/water-supply/areas/{_identifier(source_id)}", AreaDetail)

    def water_supply_geometry(self, source_id: int) -> AreaFeature:
        return self._get(f"v1/water-supply/areas/{_identifier(source_id)}/geometry", AreaFeature)

    def hydrology_dataset(self) -> HydrologyDataset:
        return self._get("v1/hydrology/dataset", HydrologyDataset)

    def hydrology_stations(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> StationPage:
        return self._get(
            "v1/hydrology/stations",
            StationPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def iter_hydrology_stations(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[Station]:
        snapshot: list[UUID | None] = [snapshot_id]

        def page(cursor: str | None) -> tuple[list[Station], str | None]:
            result = self.hydrology_stations(
                limit=page_size, after_id=cursor, snapshot_id=snapshot[0]
            )
            self._verify_snapshot(snapshot, result.dataset.snapshot_id)
            return result.items, result.next_after_id

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def hydrology_stations_near(
        self, lon: float, lat: float, *, radius_m: float = 10_000, limit: int = 50
    ) -> StationPage:
        return self._get(
            "v1/hydrology/stations/near",
            StationPage,
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            limit=limit,
        )

    def hydrology_station(self, station_id: str) -> StationDetail:
        return self._get(f"v1/hydrology/stations/{_identifier(station_id)}", StationDetail)

    def hydrology_history(
        self, retrieval_id: UUID | str, *, limit: int = 100, after: datetime | None = None
    ) -> HistoryRetrievalResponse:
        return self._get(
            f"v1/hydrology/history/{_identifier(retrieval_id)}",
            HistoryRetrievalResponse,
            limit=limit,
            after=after,
        )

    def iter_hydrology_history(
        self,
        retrieval_id: UUID | str,
        *,
        page_size: int = 1000,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[HistoricalObservation]:
        def page(cursor: datetime | None) -> tuple[list[HistoricalObservation], datetime | None]:
            result = self.hydrology_history(retrieval_id, limit=page_size, after=cursor)
            if str(result.retrieval_id) != str(retrieval_id):
                raise WaterGeoResponseError("Server changed retrieval during pagination")
            next_cursor = datetime.fromisoformat(result.next_after) if result.next_after else None
            return result.observations, next_cursor

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def catchment_dataset(self) -> CatchmentDataset:
        return self._get("v1/catchments/dataset", CatchmentDataset)

    def _catchment_page(
        self,
        resource: str,
        model: type[ModelT],
        *,
        limit: int,
        after_id: str | None,
        snapshot_id: UUID | None,
    ) -> ModelT:
        return self._get(
            f"v1/catchments/{resource}",
            model,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def river_basin_districts(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> RiverBasinDistrictPage:
        return self._catchment_page(
            "river-basin-districts",
            RiverBasinDistrictPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def management_catchments(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> ManagementCatchmentPage:
        return self._catchment_page(
            "management-catchments",
            ManagementCatchmentPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def operational_catchments(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> OperationalCatchmentPage:
        return self._catchment_page(
            "operational-catchments",
            OperationalCatchmentPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def water_bodies(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> WaterBodyPage:
        return self._catchment_page(
            "water-bodies",
            WaterBodyPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def _iter_catchments(
        self,
        fetch: Callable[..., Any],
        *,
        page_size: int,
        snapshot_id: UUID | None,
        max_pages: int,
        max_records: int,
    ) -> Iterator[Any]:
        snapshot: list[UUID | None] = [snapshot_id]

        def page(cursor: str | None) -> tuple[list[Any], str | None]:
            result = fetch(limit=page_size, after_id=cursor, snapshot_id=snapshot[0])
            self._verify_snapshot(snapshot, result.dataset.snapshot_id)
            return result.items, result.next_after_id

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def iter_river_basin_districts(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[RiverBasinDistrict]:
        return self._iter_catchments(
            self.river_basin_districts,
            page_size=page_size,
            snapshot_id=snapshot_id,
            max_pages=max_pages,
            max_records=max_records,
        )

    def iter_management_catchments(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[ManagementCatchment]:
        return self._iter_catchments(
            self.management_catchments,
            page_size=page_size,
            snapshot_id=snapshot_id,
            max_pages=max_pages,
            max_records=max_records,
        )

    def iter_operational_catchments(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[OperationalCatchment]:
        return self._iter_catchments(
            self.operational_catchments,
            page_size=page_size,
            snapshot_id=snapshot_id,
            max_pages=max_pages,
            max_records=max_records,
        )

    def iter_water_bodies(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[WaterBody]:
        return self._iter_catchments(
            self.water_bodies,
            page_size=page_size,
            snapshot_id=snapshot_id,
            max_pages=max_pages,
            max_records=max_records,
        )

    def river_basin_district(self, entity_id: str) -> RiverBasinDistrictDetail:
        return self._get(
            f"v1/catchments/river-basin-districts/{_identifier(entity_id)}",
            RiverBasinDistrictDetail,
        )

    def management_catchment(self, entity_id: str) -> ManagementCatchmentDetail:
        return self._get(
            f"v1/catchments/management-catchments/{_identifier(entity_id)}",
            ManagementCatchmentDetail,
        )

    def operational_catchment(self, entity_id: str) -> OperationalCatchmentDetail:
        return self._get(
            f"v1/catchments/operational-catchments/{_identifier(entity_id)}",
            OperationalCatchmentDetail,
        )

    def water_body(self, entity_id: str) -> WaterBodyDetail:
        return self._get(f"v1/catchments/water-bodies/{_identifier(entity_id)}", WaterBodyDetail)

    def water_body_geometry(self, entity_id: str) -> WaterBodyGeometryCollection:
        return self._get(
            f"v1/catchments/water-bodies/{_identifier(entity_id)}/geometry",
            WaterBodyGeometryCollection,
        )

    def water_quality_dataset(self, *, snapshot_id: UUID | None = None) -> WaterQualityDataset:
        return self._get("v1/water-quality/dataset", WaterQualityDataset, snapshot_id=snapshot_id)

    def water_quality_sampling_points(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> SamplingPointPage:
        return self._get(
            "v1/water-quality/sampling-points",
            SamplingPointPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def iter_water_quality_sampling_points(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[SamplingPoint]:
        snapshot: list[UUID | None] = [snapshot_id]

        def page(cursor: str | None) -> tuple[list[SamplingPoint], str | None]:
            result = self.water_quality_sampling_points(
                limit=page_size, after_id=cursor, snapshot_id=snapshot[0]
            )
            self._verify_snapshot(snapshot, result.dataset.snapshot_id)
            return result.items, result.next_after_id

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def water_quality_sampling_points_near(
        self,
        lon: float,
        lat: float,
        *,
        radius_m: float = 10_000,
        limit: int = 50,
        snapshot_id: UUID | None = None,
    ) -> SamplingPointPage:
        return self._get(
            "v1/water-quality/sampling-points/near",
            SamplingPointPage,
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            limit=limit,
            snapshot_id=snapshot_id,
        )

    def water_quality_sampling_point(
        self, sampling_point_id: str, *, snapshot_id: UUID | None = None
    ) -> SamplingPointDetail:
        return self._get(
            f"v1/water-quality/sampling-points/{_identifier(sampling_point_id)}",
            SamplingPointDetail,
            snapshot_id=snapshot_id,
        )

    def water_quality_observations(
        self, retrieval_id: UUID | str, *, limit: int = 100, after_id: str | None = None
    ) -> WaterQualityObservationRetrieval:
        return self._get(
            f"v1/water-quality/observations/{_identifier(retrieval_id)}",
            WaterQualityObservationRetrieval,
            limit=limit,
            after_id=after_id,
        )

    def iter_water_quality_observations(
        self,
        retrieval_id: UUID | str,
        *,
        page_size: int = 100,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[WaterQualityObservation]:
        def page(cursor: str | None) -> tuple[list[WaterQualityObservation], str | None]:
            result = self.water_quality_observations(retrieval_id, limit=page_size, after_id=cursor)
            if str(result.retrieval_id) != str(retrieval_id):
                raise WaterGeoResponseError("Server changed retrieval during pagination")
            return result.observations, result.next_after_id

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def reservoir_level_dataset(self, *, snapshot_id: UUID | None = None) -> ReservoirLevelDataset:
        return self._get(
            "v1/severn-trent/reservoir-levels/dataset",
            ReservoirLevelDataset,
            snapshot_id=snapshot_id,
        )

    def reservoirs(
        self, *, limit: int = 50, after_id: str | None = None, snapshot_id: UUID | None = None
    ) -> ReservoirPage:
        return self._get(
            "v1/severn-trent/reservoir-levels/reservoirs",
            ReservoirPage,
            limit=limit,
            after_id=after_id,
            snapshot_id=snapshot_id,
        )

    def iter_reservoirs(
        self,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[Reservoir]:
        snapshot: list[UUID | None] = [snapshot_id]

        def page(cursor: str | None) -> tuple[list[Reservoir], str | None]:
            result = self.reservoirs(limit=page_size, after_id=cursor, snapshot_id=snapshot[0])
            self._verify_snapshot(snapshot, result.dataset.snapshot_id)
            return result.items, result.next_after_id

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)

    def reservoirs_near(
        self,
        lon: float,
        lat: float,
        *,
        radius_m: float = 50_000,
        limit: int = 50,
        snapshot_id: UUID | None = None,
    ) -> ReservoirPage:
        return self._get(
            "v1/severn-trent/reservoir-levels/reservoirs/near",
            ReservoirPage,
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            limit=limit,
            snapshot_id=snapshot_id,
        )

    def reservoir(self, reservoir_id: str, *, snapshot_id: UUID | None = None) -> ReservoirDetail:
        return self._get(
            f"v1/severn-trent/reservoir-levels/reservoirs/{_identifier(reservoir_id)}",
            ReservoirDetail,
            snapshot_id=snapshot_id,
        )

    def reservoir_readings(
        self,
        reservoir_id: str,
        *,
        limit: int = 100,
        after: datetime | None = None,
        snapshot_id: UUID | None = None,
    ) -> ReservoirReadingPage:
        return self._get(
            f"v1/severn-trent/reservoir-levels/reservoirs/{_identifier(reservoir_id)}/readings",
            ReservoirReadingPage,
            limit=limit,
            after=after,
            snapshot_id=snapshot_id,
        )

    def iter_reservoir_readings(
        self,
        reservoir_id: str,
        *,
        page_size: int = 100,
        snapshot_id: UUID | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> Iterator[ReservoirReading]:
        snapshot: list[UUID | None] = [snapshot_id]

        def page(cursor: datetime | None) -> tuple[list[ReservoirReading], datetime | None]:
            result = self.reservoir_readings(
                reservoir_id, limit=page_size, after=cursor, snapshot_id=snapshot[0]
            )
            self._verify_snapshot(snapshot, result.dataset.snapshot_id)
            return result.items, result.next_after

        return self._iterate(lambda: page(None), page, max_pages=max_pages, max_records=max_records)
