"""Read-only public API for explicit stored hydrology history retrievals."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.hydrology_history_models import (
    HistoricalObservation,
    HistoryRetrievalResponse,
    RetrievalMetadata,
    RetrievalPage,
    RetrievalQuery,
)
from watergeo.api.water_supply_models import ApiError
from watergeo.db.hydrology_history import (
    InvalidHistoryCursor,
    get_history_retrieval,
    list_history_observations,
    list_history_retrievals,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/hydrology/history",
    tags=["hydrology-history"],
    responses={503: {"model": ApiError}},
)

Database = Annotated[Engine, Depends(get_database)]


@router.get("/retrievals", response_model=RetrievalPage)
def history_retrievals(
    response: Response, query: Annotated[RetrievalQuery, Query()], database: Database
) -> RetrievalPage:
    """Discover exact-measure editions, newest first; no ingestion or edition merging."""
    response.headers["Cache-Control"] = "no-store"
    try:
        rows, next_id = list_history_retrievals(
            database, query.measure_id, limit=query.limit, after_id=query.after_id
        )
        return RetrievalPage(
            measure_id=query.measure_id,
            items=[RetrievalMetadata(**row, licence="Open Government Licence v3") for row in rows],
            next_after_id=next_id,
        )
    except InvalidHistoryCursor:
        raise HTTPException(
            422, "Cursor does not belong to this measure", headers={"Cache-Control": "no-store"}
        ) from None
    except (SQLAlchemyError, ValidationError) as error:
        logger.warning("hydrology_history_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Hydrology history unavailable", headers={"Cache-Control": "no-store"}
        ) from None


@router.get(
    "/{retrieval_id}",
    response_model=HistoryRetrievalResponse,
    responses={404: {"model": ApiError}},
)
def history_retrieval(
    response: Response,
    retrieval_id: UUID,
    database: Database,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    after: Annotated[datetime | None, Query()] = None,
) -> HistoryRetrievalResponse:
    response.headers["Cache-Control"] = "no-store"

    if after is not None and after.tzinfo is None:
        raise HTTPException(
            422,
            "after must be timezone-aware",
            headers={"Cache-Control": "no-store"},
        )

    try:
        retrieval = get_history_retrieval(
            database,
            retrieval_id,
        )

        if retrieval is None:
            raise HTTPException(
                404,
                "Hydrology history retrieval not found",
                headers={"Cache-Control": "no-store"},
            )

        rows, next_after = list_history_observations(
            database,
            retrieval_id,
            limit=limit,
            after=after,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as error:
        logger.warning(
            "hydrology_history_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            503,
            "Hydrology history unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None

    return HistoryRetrievalResponse(
        retrieval_id=retrieval["id"],
        measure_id=retrieval["measure_id"],
        requested_from=retrieval["requested_from"],
        requested_to=retrieval["requested_to"],
        retrieval_started_at=retrieval["retrieval_started_at"],
        retrieval_completed_at=retrieval["retrieval_completed_at"],
        record_count=retrieval["record_count"],
        content_sha256=retrieval["content_sha256"],
        normalization_version=retrieval["normalization_version"],
        licence="Open Government Licence v3",
        observations=[
            HistoricalObservation(
                observed_at=row["observed_at"],
                value=row["value"],
                source_fields=row["source_fields"],
            )
            for row in rows
        ],
        next_after=next_after,
    )
