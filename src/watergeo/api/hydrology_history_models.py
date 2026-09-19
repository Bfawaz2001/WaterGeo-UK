"""Public models for bounded hydrology history retrievals."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HistoricalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    value: float | None
    source_fields: dict[str, Any]


class HistoryRetrievalResponse(BaseModel):
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
    observations: list[HistoricalObservation]
    next_after: str | None
