"""Public models for Thames Water discharge status."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watergeo.ingestion.thames_discharge import (
    API_VERSION,
    ATTRIBUTION,
    DOCUMENTATION_URL,
    LICENCE_URL,
    NATIVE_SRID,
    PUBLISHER,
    SOURCE_URL,
)

SiteId = Annotated[str, Field(pattern=r"^TWL[0-9]{5}$")]
AlertStatus = Literal["Discharging", "Not discharging", "Offline"]


class SnapshotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: UUID | None = None


class FilterQuery(SnapshotQuery):
    alert_status: AlertStatus | None = None
    alert_past_48_hours: bool | None = None


class PageQuery(FilterQuery):
    limit: int = Field(default=50, ge=1, le=100)
    after_id: SiteId | None = None


class NearQuery(FilterQuery):
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    radius_m: float = Field(default=50000, gt=0, le=200000, allow_inf_nan=False)
    limit: int = Field(default=50, ge=1, le=100)


class Dataset(BaseModel):
    snapshot_id: UUID
    publisher: str = PUBLISHER
    source_url: str = SOURCE_URL
    documentation_url: str = DOCUMENTATION_URL
    api_version: str = API_VERSION
    licence: str = "Thames Water Open Data Terms"
    licence_url: str = LICENCE_URL
    attribution: str = ATTRIBUTION
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    content_sha256: str
    normalized_sha256: str
    normalization_version: str
    site_count: int
    discharging_count: int
    offline_count: int
    source_crs: str = f"EPSG:{NATIVE_SRID}"
    response_crs: str = "EPSG:4326"
    caveat: str = (
        "Near-real-time EDM monitor indications from Thames Water. A monitor status does not "
        "establish water quality, bathing safety, discharge volume or a relationship to other "
        "WaterGeo datasets. Publisher timestamps contain no timezone offset; WaterGeo preserves "
        "them without inferring one."
    )


class Site(BaseModel):
    site_id: str
    location_name: str
    permit_number: str
    grid_reference: str
    easting: float
    northing: float
    geometry: dict[str, Any]
    receiving_watercourse: str
    alert_status: AlertStatus
    status_changed: datetime
    alert_past_48_hours: bool
    most_recent_discharge_start: datetime | None
    most_recent_discharge_stop: datetime | None
    distance_m: float | None = None


class SitePage(BaseModel):
    dataset: Dataset
    items: list[Site]
    next_after_id: str | None


class SiteDetail(Site):
    dataset: Dataset
