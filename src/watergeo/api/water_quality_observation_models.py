"""Immutable scoped observation responses, with explicit unknown source timezone."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watergeo.ingestion.water_quality import LICENCE, ROOT


class ObservationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=100, ge=1, le=100)
    after_id: str | None = Field(default=None, min_length=1, max_length=2048)


class Observation(BaseModel):
    observation_id: str
    sampling_point_id: str
    sample_id: str
    sampling_id: str
    observed_at_text: str
    time_zone_status: Literal["unspecified_by_source"] = "unspecified_by_source"
    determinand_notation: str
    unit_notation: str
    result_text: str | None
    numeric_value: float | None
    upper_bound: float | None
    lower_bound: float | None
    publisher_sample: dict[str, Any]


class ObservationRetrieval(BaseModel):
    retrieval_id: UUID
    sampling_point_snapshot_id: UUID
    sampling_point_id: str
    date_from: date
    date_to: date
    determinand: dict[str, Any]
    units: list[dict[str, Any]]
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    content_sha256: str
    normalized_sha256: str
    normalization_version: str
    record_count: int
    source_api: str = ROOT
    publisher: str = "Environment Agency"
    licence: str = "Open Government Licence v3"
    licence_url: str = LICENCE
    attribution: str = (
        "Contains Environment Agency information © Environment Agency and/or database right."
    )
    observations: list[Observation]
    next_after_id: str | None
    caveat: str = (
        "Explicit bounded retrieval; start-inclusive/end-exclusive dates, no assumed timezone. "
        "Retrieval time is separate from phenomenonTime. Censored bounds are not measured values. "
        "Units are not converted. Later corrected evidence coexists; "
        "pages are not publisher-atomic. "
        "Sample/purpose/material relationships and identifiers are publisher facts."
    )
