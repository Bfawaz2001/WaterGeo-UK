"""Read-only API for the reviewed Severn Trent reservoir-level edition."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.stream_reservoir_models import (
    Dataset,
    NearQuery,
    PageQuery,
    ReadingPage,
    ReadingQuery,
    ReservoirDetail,
    ReservoirId,
    ReservoirPage,
    SnapshotQuery,
)
from watergeo.api.water_supply_models import ApiError
from watergeo.db.stream_reservoirs import (
    ReservoirNotFound,
    StreamReservoirQueries,
    StreamReservoirUnavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/severn-trent/reservoir-levels",
    tags=["severn-trent-reservoir-levels"],
    responses={503: {"model": ApiError}},
)


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[StreamReservoirQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield StreamReservoirQueries(engine)
    except ReservoirNotFound:
        raise HTTPException(
            404, "Reservoir not found", headers={"Cache-Control": "no-store"}
        ) from None
    except (SQLAlchemyError, StreamReservoirUnavailable, ValidationError) as error:
        logger.warning("stream_reservoir_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Reservoir-level dataset unavailable", headers={"Cache-Control": "no-store"}
        ) from None


Queries = Annotated[StreamReservoirQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset(query.snapshot_id)


@router.get("/reservoirs")
def reservoirs(query: Annotated[PageQuery, Query()], db: Queries) -> ReservoirPage:
    return db.reservoirs(db.dataset(query.snapshot_id), limit=query.limit, after_id=query.after_id)


@router.get("/reservoirs/near")
def near(query: Annotated[NearQuery, Query()], db: Queries) -> ReservoirPage:
    return db.reservoirs(
        db.dataset(query.snapshot_id),
        limit=query.limit,
        point=(query.lon, query.lat, query.radius_m),
    )


@router.get("/reservoirs/{reservoir_id}", responses={404: {"model": ApiError}})
def reservoir(
    reservoir_id: ReservoirId,
    query: Annotated[SnapshotQuery, Query()],
    db: Queries,
) -> ReservoirDetail:
    dataset = db.dataset(query.snapshot_id)
    return db.reservoir(dataset, reservoir_id)


@router.get("/reservoirs/{reservoir_id}/readings", responses={404: {"model": ApiError}})
def readings(
    reservoir_id: ReservoirId,
    query: Annotated[ReadingQuery, Query()],
    db: Queries,
) -> ReadingPage:
    dataset = db.dataset(query.snapshot_id)
    return db.readings(dataset, reservoir_id, limit=query.limit, after=query.after)
