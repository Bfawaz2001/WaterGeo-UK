"""Public models for one reviewed Severn Trent Water reservoir-level edition."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from watergeo.ingestion.stream_reservoirs import (
    ATTRIBUTION,
    EDITION,
    LICENCE,
    LICENCE_URL,
    NATIVE_SRID,
    PUBLIC_ITEM_URL,
    PUBLISHER,
    SERVICE_ROOT,
)

ReservoirId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]


class SnapshotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: UUID | None = None


class PageQuery(SnapshotQuery):
    limit: int = Field(default=50, ge=1, le=100)
    after_id: ReservoirId | None = None


class NearQuery(SnapshotQuery):
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    radius_m: float = Field(default=50000, gt=0, le=200000, allow_inf_nan=False)
    limit: int = Field(default=50, ge=1, le=100)


class ReadingQuery(SnapshotQuery):
    limit: int = Field(default=100, ge=1, le=100)
    after: AwareDatetime | None = None


class Dataset(BaseModel):
    snapshot_id: UUID
    publisher: str = PUBLISHER
    source_item: str = PUBLIC_ITEM_URL
    source_service: str = SERVICE_ROOT
    edition: str = EDITION
    licence: str = LICENCE
    licence_url: str = LICENCE_URL
    attribution: str = ATTRIBUTION
    source_item_created_at: datetime
    source_item_modified_at: datetime
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    content_sha256: str
    normalized_sha256: str
    normalization_version: str
    reservoir_count: int
    reading_count: int
    source_crs: str = f"EPSG:{NATIVE_SRID}"
    response_crs: str = "EPSG:4326"
    caveat: str = (
        "A dated 2025 publisher edition, not current supply status. Points are source-provided "
        "locations, not reservoir footprints. Capacity meanings can differ across companies. "
        "Do not infer restrictions, safety, risk, company service areas or links to other "
        "WaterGeo datasets. The source DATE field declares UTC; exact timestamps are preserved."
    )


class Reading(BaseModel):
    observed_at: datetime
    current_level: float
    current_level_unit: str
    current_percentage: float


class Reservoir(BaseModel):
    reservoir_id: str
    name: str
    latitude: float
    longitude: float
    geometry: dict[str, Any]
    capacity: float
    capacity_unit: str
    distance_m: float | None = None
    latest_reading: Reading | None = None


class ReservoirPage(BaseModel):
    dataset: Dataset
    items: list[Reservoir]
    next_after_id: str | None


class ReservoirDetail(Reservoir):
    dataset: Dataset


class ReadingPage(BaseModel):
    dataset: Dataset
    reservoir: Reservoir
    items: list[Reading]
    next_after: datetime | None
    timestamp_note: str = (
        "Exact publisher UTC instants. Summer records occur at 23:00 UTC on the preceding "
        "calendar day; WaterGeo does not infer a local date."
    )
