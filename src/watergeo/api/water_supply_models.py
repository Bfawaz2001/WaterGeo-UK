"""Public contracts for the reviewed water-supply dataset."""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from watergeo.core.presentation import (
    REVIEWED_WGS84_GEOMETRIES,
    WGS84_PRESENTATION_REVIEW,
    WGS84_PRESENTATION_VERSION,
)


def decimal_integer(value: object) -> object:
    """Reject decimal/exponent notation and signs in HTTP integer parameters."""
    if isinstance(value, str) and not re.fullmatch(r"[0-9]{1,19}", value):
        raise ValueError("Use an unsigned decimal integer.")
    return value


SourceId = Annotated[int, BeforeValidator(decimal_integer), Field(ge=1, le=2**63 - 1)]
Cursor = Annotated[int, BeforeValidator(decimal_integer), Field(ge=0, le=2**63 - 1)]
PageSize = Annotated[int, BeforeValidator(decimal_integer), Field(ge=1, le=100)]


class NoQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AreaQuery(NoQuery):
    limit: PageSize = 50
    after_id: Cursor = 0


class PointQuery(AreaQuery):
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)


class ApiError(BaseModel):
    detail: str


class DatasetMetadata(BaseModel):
    dataset: Literal["ofwat-water-supply-areas"] = "ofwat-water-supply-areas"
    release: Literal["v1_5"] = "v1_5"
    release_month: Literal["2024-04"] = "2024-04"
    snapshot_id: UUID
    source_sha256: str
    source_url: str
    source_bytes: int
    retrieved_at: datetime
    ingested_at: datetime
    publisher: str
    distributor: str
    licence_name: str
    licence_version: str | None
    licence_url: str
    attribution: str
    transformation_version: str
    presentation_version: str = WGS84_PRESENTATION_VERSION
    presentation_review_reference: str = WGS84_PRESENTATION_REVIEW
    presentation_exception_source_ids: tuple[int, ...] = tuple(REVIEWED_WGS84_GEOMETRIES)
    area_count: int
    transformed_area_count: int
    stored_crs: Literal["EPSG:27700"] = "EPSG:27700"
    geojson_coordinates: str = "WGS84 longitude, latitude (EPSG:4326)"
    disclaimer: str = (
        "Dated boundaries for geospatial analysis, including reviewed WaterGeo transformations. "
        "The definitive legal record remains company appointments and variations. "
        "Premises exceptions, seaward approximation and omitted islands may affect coverage. "
        "A match does not establish a property's current supplier."
    )


class AreaSummary(BaseModel):
    source_id: int
    area_served: str | None
    company: str | None
    company_acronym: str | None
    company_type: str | None
    area_type: str | None
    source_version: str | None
    source_last_update: date | None
    warnings: str | None
    transformed: bool


class AreaPage(BaseModel):
    snapshot_id: UUID
    dataset_url: str = "/v1/water-supply/dataset"
    items: list[AreaSummary]
    next_after_id: int | None


class TransformationMetadata(BaseModel):
    transformation_id: str
    method: str
    keep_collapsed: bool
    shapely_version: str
    geos_version: str
    invalid_reason: str
    source_decoded_wkb_sha256: str
    canonical_wkb_sha256: str
    review_status: str
    review_reason: str
    review_reference: str
    transformed_at: datetime


class AreaDetail(AreaSummary):
    snapshot_id: UUID
    dataset_url: str = "/v1/water-supply/dataset"
    geometry_url: str
    licence_statement: str | None
    source_provenance: str | None
    disclaimer: str | None
    premises_disclaimer: str | None
    coastline_disclaimer: str | None
    transformation: TransformationMetadata | None


class MultiPolygon(BaseModel):
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: list[list[list[tuple[float, float]]]]


class PresentationMetadata(BaseModel):
    policy_version: str = WGS84_PRESENTATION_VERSION
    review_reference: str = WGS84_PRESENTATION_REVIEW
    method: Literal["reprojection", "post_transform_structure"]
    canonical_geometry_changed: Literal[False] = False
    canonical_wkb_sha256: str | None
    geometry_geojson_sha256: str
    hash_encoding: str = (
        "SHA-256 of PostGIS 15-decimal GeoJSON UTF-8 text before HTTP serialization"
    )
    output_crs: Literal["EPSG:4326"] = "EPSG:4326"
    decimal_places: Literal[15] = 15


class AreaFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    properties: AreaDetail
    geometry: MultiPolygon
    presentation: PresentationMetadata
