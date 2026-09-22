"""Snapshot-pinned sampling points; publisher identifiers are opaque, not slugs."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watergeo.ingestion.water_quality import ID_PATTERN, LICENCE, ROOT

PointId = Annotated[str, Field(pattern=ID_PATTERN.pattern)]


class SnapshotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: UUID | None = None


class PageQuery(SnapshotQuery):
    limit: int = Field(default=50, ge=1, le=100)
    after_id: PointId | None = None


class NearQuery(SnapshotQuery):
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    radius_m: float = Field(default=10000, gt=0, le=100000, allow_inf_nan=False)
    limit: int = Field(default=50, ge=1, le=100)


class Dataset(BaseModel):
    snapshot_id: UUID
    publisher: str = "Environment Agency"
    source_api: str = ROOT
    licence: str = "Open Government Licence v3"
    licence_url: str = LICENCE
    attribution: str = (
        "Contains Environment Agency information © Environment Agency and/or database right."
    )
    api_version: str = "1"
    content_sha256: str
    normalized_sha256: str
    normalization_version: str
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    sampling_point_count: int
    sampling_point_with_location_count: int
    sampling_point_without_location_count: int
    caveat: str = (
        "Mutable publisher metadata, not a publisher-atomic release or observation record. "
        "Region, area and sub-area are publisher metadata; no company, catchment or "
        "Hydrology relationship is inferred. WGS84 locations are publisher supplied."
    )


class SamplingPoint(BaseModel):
    sampling_point_id: str
    source_uri: str
    alt_label: str
    pref_label: str | None
    latitude: float | None
    longitude: float | None
    geometry: dict[str, Any] | None
    location_status: Literal["available", "unavailable"]
    distance_m: float | None = None


class SamplingPointDetail(SamplingPoint):
    dataset: Dataset
    publisher_metadata: dict[str, Any]


class SamplingPointPage(BaseModel):
    dataset: Dataset
    items: list[SamplingPoint]
    next_after_id: str | None
    spatial_exclusion_note: str | None = None
