"""Public contracts for Catchment Data Explorer Cycle 3."""

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from watergeo.ingestion.catchments import IDENTITY_PATTERN

CatchmentId = Annotated[str, Field(pattern=IDENTITY_PATTERN.pattern)]


def decimal_integer(value: object) -> object:
    """Reject decimal/exponent notation and signs in HTTP integer parameters."""
    if isinstance(value, str) and not re.fullmatch(r"[0-9]{1,3}", value):
        raise ValueError("Use an unsigned decimal integer.")
    return value


PageSize = Annotated[
    int,
    BeforeValidator(decimal_integer),
    Field(ge=1, le=100),
]


class NoQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageQuery(NoQuery):
    limit: PageSize = 50
    after_id: CatchmentId | None = None
    snapshot_id: UUID | None = None


class Dataset(BaseModel):
    dataset: Literal["environment-agency-catchment-data-explorer"] = (
        "environment-agency-catchment-data-explorer"
    )
    snapshot_id: UUID
    publisher: Literal["Environment Agency"] = "Environment Agency"
    source_url: str
    plan_version: Literal["c3-plan"]
    normalization_version: str
    content_sha256: str
    normalized_sha256: str
    retrieval_started_at: datetime
    retrieval_completed_at: datetime
    river_basin_district_count: int
    management_catchment_count: int
    operational_catchment_count: int
    water_body_count: int
    geometry_feature_count: int
    geographic_coverage: Literal["England"] = "England"
    licence: Literal["Open Government Licence"] = "Open Government Licence"
    attribution: str
    request_manifest: dict[str, Any]
    hierarchy: Literal[
        "River Basin District -> Management Catchment -> Operational Catchment -> Water Body"
    ] = "River Basin District -> Management Catchment -> Operational Catchment -> Water Body"
    relationship_caveat: str = (
        "This dataset does not assert a Hydrology station-to-catchment relationship."
    )


class RiverBasinDistrict(BaseModel):
    river_basin_district_id: str
    name: str
    publisher_uri: str


class RiverBasinDistrictDetail(RiverBasinDistrict):
    snapshot_id: UUID
    source_fields: dict[str, Any]


class ManagementCatchment(BaseModel):
    management_catchment_id: str
    river_basin_district_id: str
    name: str
    publisher_uri: str


class ManagementCatchmentDetail(ManagementCatchment):
    snapshot_id: UUID
    source_fields: dict[str, Any]


class OperationalCatchment(BaseModel):
    operational_catchment_id: str
    management_catchment_id: str
    river_basin_district_id: str
    name: str
    publisher_uri: str


class OperationalCatchmentDetail(OperationalCatchment):
    snapshot_id: UUID
    source_fields: dict[str, Any]


class WaterBody(BaseModel):
    water_body_id: str
    operational_catchment_id: str
    management_catchment_id: str
    river_basin_district_id: str
    name: str
    water_body_type: str | None
    publisher_uri: str


class WaterBodyDetail(WaterBody):
    snapshot_id: UUID
    source_fields: dict[str, Any]
    geometry_url: str


class RiverBasinDistrictPage(BaseModel):
    dataset: Dataset
    items: list[RiverBasinDistrict]
    next_after_id: str | None


class ManagementCatchmentPage(BaseModel):
    dataset: Dataset
    items: list[ManagementCatchment]
    next_after_id: str | None


class OperationalCatchmentPage(BaseModel):
    dataset: Dataset
    items: list[OperationalCatchment]
    next_after_id: str | None


class WaterBodyPage(BaseModel):
    dataset: Dataset
    items: list[WaterBody]
    next_after_id: str | None


class GeoJSONGeometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon", "LineString", "MultiLineString"]
    coordinates: Any


class WaterBodyGeometryFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONGeometry
    properties: dict[str, Any]


class WaterBodyGeometryCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    water_body_id: str
    snapshot_id: UUID
    features: list[WaterBodyGeometryFeature]
