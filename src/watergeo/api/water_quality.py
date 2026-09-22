"""Sampling-point API preserving literal publisher spaces and slash notation."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.water_quality_models import (
    Dataset,
    NearQuery,
    PageQuery,
    PointId,
    SamplingPointDetail,
    SamplingPointPage,
    SnapshotQuery,
)
from watergeo.api.water_supply_models import ApiError
from watergeo.db.water_quality import (
    SamplingPointNotFound,
    WaterQualityQueries,
    WaterQualityUnavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/water-quality", tags=["water-quality"], responses={503: {"model": ApiError}}
)


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[WaterQualityQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield WaterQualityQueries(engine)
    except SamplingPointNotFound:
        raise HTTPException(
            404, "Sampling point not found", headers={"Cache-Control": "no-store"}
        ) from None
    except (SQLAlchemyError, WaterQualityUnavailable, ValidationError) as error:
        logger.warning("water_quality_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Water quality dataset unavailable", headers={"Cache-Control": "no-store"}
        ) from None


Queries = Annotated[WaterQualityQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset(query.snapshot_id)


@router.get("/sampling-points")
def sampling_points(query: Annotated[PageQuery, Query()], db: Queries) -> SamplingPointPage:
    return db.points(db.dataset(query.snapshot_id), limit=query.limit, after_id=query.after_id)


@router.get("/sampling-points/near")
def near(query: Annotated[NearQuery, Query()], db: Queries) -> SamplingPointPage:
    return db.points(
        db.dataset(query.snapshot_id),
        limit=query.limit,
        point=(query.lon, query.lat, query.radius_m),
    )


@router.get("/sampling-points/{sampling_point_id:path}", responses={404: {"model": ApiError}})
def sampling_point(
    sampling_point_id: PointId, query: Annotated[SnapshotQuery, Query()], db: Queries
) -> SamplingPointDetail:
    return db.point(db.dataset(query.snapshot_id), sampling_point_id)
