"""Bounded search endpoint for the WaterGeo product explorer."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.search_models import SearchQuery, SearchResponse
from watergeo.api.water_supply_models import ApiError
from watergeo.db.search import SearchQueries

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/search",
    tags=["search"],
    responses={503: {"model": ApiError, "description": "Search unavailable"}},
)


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[SearchQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield SearchQueries(engine)
    except (SQLAlchemyError, ValidationError) as error:
        logger.warning("search_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "WaterGeo search unavailable", headers={"Cache-Control": "no-store"}
        ) from None


Queries = Annotated[SearchQueries, Depends(queries)]


@router.get("")
def search(query: Annotated[SearchQuery, Query()], db: Queries) -> SearchResponse:
    """Search current compatible snapshots by exact identity or name prefix."""
    return db.search(query.q, limit=query.limit)
