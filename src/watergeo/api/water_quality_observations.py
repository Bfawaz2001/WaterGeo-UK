"""Public bounded Water Quality observation evidence, never an upstream live query."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.water_quality_observation_models import ObservationQuery, ObservationRetrieval
from watergeo.api.water_supply_models import ApiError
from watergeo.db.water_quality_observations import retrieval

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/water-quality/observations",
    tags=["water-quality"],
    responses={503: {"model": ApiError}},
)


@router.get("/{retrieval_id}", responses={404: {"model": ApiError}})
def observations(
    retrieval_id: UUID,
    query: Annotated[ObservationQuery, Query()],
    response: Response,
    engine: Annotated[Engine, Depends(get_database)],
) -> ObservationRetrieval:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = retrieval(engine, retrieval_id, limit=query.limit, after_id=query.after_id)
    except (SQLAlchemyError, ValidationError) as error:
        logger.warning(
            "water_quality_observations_unavailable", extra={"error_type": type(error).__name__}
        )
        raise HTTPException(
            503, "Water quality observations unavailable", headers={"Cache-Control": "no-store"}
        ) from None
    if result is None:
        raise HTTPException(
            404, "Observation retrieval not found", headers={"Cache-Control": "no-store"}
        )
    return result
