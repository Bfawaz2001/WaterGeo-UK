"""Read-only Environment Agency hydrology endpoints."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.hydrology_models import (
    Dataset,
    NearQuery,
    PageQuery,
    StationDetail,
    StationId,
    StationPage,
)
from watergeo.api.water_supply_models import ApiError, NoQuery
from watergeo.db.hydrology import HydrologyQueries, HydrologyUnavailable, StationNotFound

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/hydrology", tags=["hydrology"], responses={503: {"model": ApiError}})


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[HydrologyQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield HydrologyQueries(engine)
    except StationNotFound:
        raise HTTPException(
            404, "Station not found", headers={"Cache-Control": "no-store"}
        ) from None
    except (SQLAlchemyError, HydrologyUnavailable, ValidationError) as error:
        logger.warning("hydrology_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Hydrology dataset unavailable", headers={"Cache-Control": "no-store"}
        ) from None


Queries = Annotated[HydrologyQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[NoQuery, Query()], db: Queries) -> Dataset:
    return db.dataset()


@router.get("/stations")
def stations(query: Annotated[PageQuery, Query()], db: Queries) -> StationPage:
    """Pass snapshot_id and next_after_id on subsequent pages to keep a stable snapshot."""
    return db.stations(db.dataset(query.snapshot_id), limit=query.limit, after_id=query.after_id)


@router.get("/stations/near")
def near(query: Annotated[NearQuery, Query()], db: Queries) -> StationPage:
    """WGS84 spheroidal geography distance in metres; unlocated stations excluded."""
    return db.stations(
        db.dataset(), limit=query.limit, point=(query.lon, query.lat, query.radius_m)
    )


@router.get("/stations/{station_id}", responses={404: {"model": ApiError}})
def station(
    station_id: StationId, query: Annotated[NoQuery, Query()], db: Queries
) -> StationDetail:
    return db.station(db.dataset(), station_id)
