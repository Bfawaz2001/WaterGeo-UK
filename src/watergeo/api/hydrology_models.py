"""Bounded hydrology inputs and explicit location/freshness responses."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watergeo.ingestion.hydrology import ID_PATTERN

StationId = Annotated[str, Field(pattern=ID_PATTERN)]


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=100)
    after_id: StationId | None = None
    snapshot_id: UUID | None = None


class NearQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    radius_m: float = Field(default=10000, gt=0, le=100000, allow_inf_nan=False)
    limit: int = Field(default=50, ge=1, le=100)


class Dataset(BaseModel):
    snapshot_id: UUID
    publisher: str
    source_api: str
    documentation_url: str
    licence: str
    licence_url: str
    attribution: str
    geographic_coverage: str
    scope: list[str]
    content_sha256: str
    normalization_version: str
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    station_count: int
    station_with_location_count: int
    station_without_location_count: int
    measure_count: int
    latest_observation_count: int
    freshness_caveat: str
    request_manifest: dict[str, Any]


class Station(BaseModel):
    station_id: str
    source_uri: str
    labels: list[str]
    location_status: Literal["available", "unavailable"]
    latitude: float | None
    longitude: float | None
    geometry: dict[str, Any] | None
    distance_m: float | None = None


class Observation(BaseModel):
    observed_at: datetime
    value: float | None
    source_fields: dict[str, Any]


class Measure(BaseModel):
    measure_id: str
    source_uri: str
    parameter: str
    unit_name: str
    period: int
    source_fields: dict[str, Any]
    latest_observation: Observation | None


class StationDetail(Station):
    dataset: Dataset
    source_fields: dict[str, Any]
    measures: list[Measure]


class StationPage(BaseModel):
    dataset: Dataset
    items: list[Station]
    next_after_id: str | None
    spatial_exclusion_note: str | None = None
