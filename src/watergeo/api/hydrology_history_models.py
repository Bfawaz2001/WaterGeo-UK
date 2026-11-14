"""Public models for bounded hydrology history retrievals."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watergeo.api.hydrology_models import StationId


class HistoricalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    value: float | None
    source_fields: dict[str, Any]


class HistoryRetrievalMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_id: UUID
    measure_id: str
    requested_from: datetime
    requested_to: datetime
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    record_count: int
    content_sha256: str
    normalization_version: str
    licence: str


class HistoryRetrievalResponse(HistoryRetrievalMetadata):
    observations: list[HistoricalObservation]
    next_after: str | None


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure_id: StationId
    limit: int = Field(default=50, ge=1, le=100)
    after_id: UUID | None = None


class RetrievalMetadata(HistoryRetrievalMetadata):
    normalized_sha256: str


class RetrievalPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure_id: str
    items: list[RetrievalMetadata]
    next_after_id: UUID | None
