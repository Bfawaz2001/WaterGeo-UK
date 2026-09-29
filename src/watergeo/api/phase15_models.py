"""Public models for Phase 15 national products."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class Dataset(BaseModel):
    snapshot_id: UUID
    source: str
    publisher: str
    source_url: str
    licence: str
    licence_url: str
    attribution: str
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    content_sha256: str
    normalized_sha256: str
    normalization_version: str
    entity_count: int
    secondary_count: int
    skipped_count: int
    caveat: str


class Page(BaseModel):
    dataset: Dataset
    items: list[dict[str, Any]]
    next_after_id: str | None


class Detail(BaseModel):
    dataset: Dataset
    item: dict[str, Any]
