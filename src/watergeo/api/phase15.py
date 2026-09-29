"""Read-only API routes for Phase 15 national products."""

import logging
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.phase15_models import Dataset, Detail, Page
from watergeo.db.phase15 import Phase15NotFound, Phase15Queries, Phase15Unavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["national-data"])


class SnapshotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: UUID | None = None


class PageQuery(SnapshotQuery):
    limit: int = Field(default=50, ge=1, le=100)
    after_id: str | None = Field(default=None, max_length=160)


class NearQuery(SnapshotQuery):
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    radius_m: float = Field(default=50000, gt=0, le=200000, allow_inf_nan=False)
    limit: int = Field(default=50, ge=1, le=100)


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[Phase15Queries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield Phase15Queries(engine)
    except Phase15NotFound:
        raise HTTPException(404, "National source entity not found") from None
    except (SQLAlchemyError, Phase15Unavailable) as error:
        logger.warning("national_source_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(503, "National source dataset unavailable") from None


Queries = Annotated[Phase15Queries, Depends(queries)]


@router.get("/rainfall/dataset")
def rainfall_dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset("rainfall", query.snapshot_id)


@router.get("/rainfall/stations")
def rainfall_stations(query: Annotated[PageQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("rainfall", query.snapshot_id)
    return db.rainfall(dataset, limit=query.limit, after=query.after_id, near=None)


@router.get("/rainfall/stations/near")
def rainfall_near(query: Annotated[NearQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("rainfall", query.snapshot_id)
    return db.rainfall(
        dataset, limit=query.limit, after=None, near=(query.lon, query.lat, query.radius_m)
    )


@router.get("/rainfall/stations/{station_id}")
def rainfall_station(
    station_id: str, query: Annotated[SnapshotQuery, Query()], db: Queries
) -> Detail:
    return db.detail("rainfall", db.dataset("rainfall", query.snapshot_id), station_id)


@router.get("/flood-monitoring/dataset")
def flood_dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset("flood-monitoring", query.snapshot_id)


@router.get("/flood-monitoring/areas")
def flood_areas(
    query: Annotated[SnapshotQuery, Query()], db: Queries, warnings_only: bool = False
) -> Page:
    dataset = db.dataset("flood-monitoring", query.snapshot_id)
    items = db.flood_areas(dataset, warnings_only=warnings_only)
    return Page(dataset=dataset, items=items, next_after_id=None)


@router.get("/flood-monitoring/warnings")
def flood_warnings(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("flood-monitoring", query.snapshot_id)
    return Page(
        dataset=dataset, items=db.flood_areas(dataset, warnings_only=True), next_after_id=None
    )


@router.get("/bathing-waters/dataset")
def bathing_dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset("bathing-waters", query.snapshot_id)


@router.get("/bathing-waters")
def bathing_waters(query: Annotated[PageQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("bathing-waters", query.snapshot_id)
    return db.bathing(dataset, limit=query.limit, after=query.after_id, near=None)


@router.get("/bathing-waters/near")
def bathing_near(query: Annotated[NearQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("bathing-waters", query.snapshot_id)
    return db.bathing(
        dataset, limit=query.limit, after=None, near=(query.lon, query.lat, query.radius_m)
    )


@router.get("/bathing-waters/{bathing_water_id}")
def bathing_water(
    bathing_water_id: str, query: Annotated[SnapshotQuery, Query()], db: Queries
) -> Detail:
    return db.detail(
        "bathing-waters", db.dataset("bathing-waters", query.snapshot_id), bathing_water_id
    )


@router.get("/company-performance/dataset")
def performance_dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset("company-performance", query.snapshot_id)


@router.get("/company-performance/companies")
def companies(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Page:
    dataset = db.dataset("company-performance", query.snapshot_id)
    return Page(dataset=dataset, items=db.companies(dataset), next_after_id=None)


@router.get("/company-performance/companies/{company_id}")
def company(company_id: str, query: Annotated[SnapshotQuery, Query()], db: Queries) -> Detail:
    dataset = db.dataset("company-performance", query.snapshot_id)
    return db.measures(dataset, company_id, period=None, measure=None)


@router.get("/company-performance/companies/{company_id}/measures")
def company_measures(
    company_id: str,
    query: Annotated[SnapshotQuery, Query()],
    db: Queries,
    reporting_period: str | None = None,
    measure_code: str | None = None,
) -> Detail:
    dataset = db.dataset("company-performance", query.snapshot_id)
    return db.measures(dataset, company_id, period=reporting_period, measure=measure_code)
