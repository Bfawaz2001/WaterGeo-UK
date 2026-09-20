"""Read-only source availability and explicit operational freshness policy."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.source_models import SourceStatuses
from watergeo.api.water_supply_models import ApiError, NoQuery
from watergeo.db.source_status import source_statuses

router = APIRouter(prefix="/v1/sources", tags=["sources"])
logger = logging.getLogger(__name__)


@router.get("/status", responses={503: {"model": ApiError}})
def status(
    query: Annotated[NoQuery, Query()],
    response: Response,
    request: Request,
    engine: Annotated[Engine, Depends(get_database)],
) -> SourceStatuses:
    response.headers["Cache-Control"] = "no-store"
    try:
        return source_statuses(engine, request.app.state.settings)
    except (SQLAlchemyError, ValidationError) as error:
        logger.warning("source_status_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Source status unavailable", headers={"Cache-Control": "no-store"}
        ) from None
