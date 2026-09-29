"""Bounded product search across the latest compatible WaterGeo snapshots."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SearchKind = Literal[
    "hydrology",
    "rainfall",
    "water-quality",
    "flood-warnings",
    "bathing-waters",
    "reservoirs",
    "thames-discharge",
    "water-body",
    "water-supply",
]
SearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=80),
]


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchText
    limit: int = Field(default=24, ge=1, le=30)


class SearchResult(BaseModel):
    kind: SearchKind
    identity: str
    label: str
    context: str
    publisher: str
    snapshot_id: UUID
    longitude: float | None
    latitude: float | None


class SearchResponse(BaseModel):
    query: str
    items: list[SearchResult]
    truncated: bool
    available_kinds: list[SearchKind]
    unavailable_kinds: list[SearchKind]
