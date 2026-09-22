"""Operational ages describe accepted local evidence, not publisher guarantees."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SourceName = Literal["ofwat", "hydrology", "hydrology-history", "catchments", "water-quality"]
Freshness = Literal["current", "stale", "unknown", "not_applicable"]


class SourceStatus(BaseModel):
    source: SourceName
    semantics: Literal["versioned_release", "dynamic_snapshot", "bounded_history", "versioned_plan"]
    availability: Literal["available", "unavailable"]
    snapshot_id: UUID | None = None
    content_sha256: str | None = None
    normalization_version: str
    source_version: str | None = None
    retrieval_started_at: datetime | None = None
    retrieved_at: datetime | None = None
    snapshot_age_seconds: float | None = None
    retrieval_freshness: Freshness = "unknown"
    retrieval_max_age_seconds: int | None = None
    observation_oldest_at: datetime | None = None
    observation_newest_at: datetime | None = None
    oldest_observation_age_seconds: float | None = None
    newest_observation_age_seconds: float | None = None
    observation_count: int | None = None
    missing_value_count: int | None = None
    measures_without_observation_count: int | None = None
    observation_freshness: Freshness = "not_applicable"
    observation_max_age_seconds: int | None = None
    measure_id: str | None = None
    requested_from: datetime | None = None
    requested_to: datetime | None = None
    caveat: str


class SourceStatuses(BaseModel):
    checked_at: datetime
    sources: list[SourceStatus]
