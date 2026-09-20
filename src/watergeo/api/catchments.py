"""Public read-only Catchment Data Explorer routes."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.catchment_models import (
    CatchmentId,
    Dataset,
    ManagementCatchmentDetail,
    ManagementCatchmentPage,
    NoQuery,
    OperationalCatchmentDetail,
    OperationalCatchmentPage,
    PageQuery,
    RiverBasinDistrictDetail,
    RiverBasinDistrictPage,
    WaterBodyDetail,
    WaterBodyGeometryCollection,
    WaterBodyPage,
)
from watergeo.api.dependencies import get_database
from watergeo.api.water_supply_models import ApiError
from watergeo.db.catchments import (
    CatchmentEntityNotFound,
    CatchmentGeometryTooLarge,
    CatchmentQueries,
    CatchmentUnavailable,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/catchments",
    tags=["catchments"],
    responses={503: {"model": ApiError, "description": "Dataset unavailable"}},
)


class GeoJSONResponse(JSONResponse):
    media_type = "application/geo+json"


def queries(
    response: Response,
    engine: Annotated[Engine, Depends(get_database)],
) -> Iterator[CatchmentQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield CatchmentQueries(engine)
    except CatchmentEntityNotFound:
        raise HTTPException(
            404,
            "Catchment entity not found",
            headers={"Cache-Control": "no-store"},
        ) from None
    except CatchmentGeometryTooLarge:
        raise HTTPException(
            413,
            "Geometry exceeds the 8 MiB output limit",
            headers={"Cache-Control": "no-store"},
        ) from None
    except (SQLAlchemyError, CatchmentUnavailable, ValidationError) as error:
        logger.warning(
            "catchment_dataset_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            503,
            "Catchment dataset unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None


Queries = Annotated[CatchmentQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[NoQuery, Query()], db: Queries) -> Dataset:
    return db.dataset()


@router.get("/river-basin-districts")
def river_basin_districts(
    query: Annotated[PageQuery, Query()], db: Queries
) -> RiverBasinDistrictPage:
    selected = db.dataset(query.snapshot_id)
    return db.river_basin_districts(
        selected,
        limit=query.limit,
        after_id=query.after_id,
    )


@router.get(
    "/river-basin-districts/{entity_id}",
    responses={404: {"model": ApiError}},
)
def river_basin_district(
    entity_id: CatchmentId,
    query: Annotated[NoQuery, Query()],
    db: Queries,
) -> RiverBasinDistrictDetail:
    return db.river_basin_district(db.dataset(), entity_id)


@router.get("/management-catchments")
def management_catchments(
    query: Annotated[PageQuery, Query()], db: Queries
) -> ManagementCatchmentPage:
    selected = db.dataset(query.snapshot_id)
    return db.management_catchments(
        selected,
        limit=query.limit,
        after_id=query.after_id,
    )


@router.get(
    "/management-catchments/{entity_id}",
    responses={404: {"model": ApiError}},
)
def management_catchment(
    entity_id: CatchmentId,
    query: Annotated[NoQuery, Query()],
    db: Queries,
) -> ManagementCatchmentDetail:
    return db.management_catchment(db.dataset(), entity_id)


@router.get("/operational-catchments")
def operational_catchments(
    query: Annotated[PageQuery, Query()], db: Queries
) -> OperationalCatchmentPage:
    selected = db.dataset(query.snapshot_id)
    return db.operational_catchments(
        selected,
        limit=query.limit,
        after_id=query.after_id,
    )


@router.get(
    "/operational-catchments/{entity_id}",
    responses={404: {"model": ApiError}},
)
def operational_catchment(
    entity_id: CatchmentId,
    query: Annotated[NoQuery, Query()],
    db: Queries,
) -> OperationalCatchmentDetail:
    return db.operational_catchment(db.dataset(), entity_id)


@router.get("/water-bodies")
def water_bodies(query: Annotated[PageQuery, Query()], db: Queries) -> WaterBodyPage:
    selected = db.dataset(query.snapshot_id)
    return db.water_bodies(
        selected,
        limit=query.limit,
        after_id=query.after_id,
    )


@router.get(
    "/water-bodies/{entity_id}",
    responses={404: {"model": ApiError}},
)
def water_body(
    entity_id: CatchmentId,
    query: Annotated[NoQuery, Query()],
    db: Queries,
) -> WaterBodyDetail:
    return db.water_body(db.dataset(), entity_id)


@router.get(
    "/water-bodies/{entity_id}/geometry",
    response_class=GeoJSONResponse,
    responses={
        404: {"model": ApiError},
        413: {"model": ApiError},
    },
)
def water_body_geometry(
    entity_id: CatchmentId,
    query: Annotated[NoQuery, Query()],
    db: Queries,
) -> WaterBodyGeometryCollection:
    return db.water_body_geometry(db.dataset(), entity_id)
