"""Read-only API for Thames Water discharge status."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.thames_discharge_models import (
    Dataset,
    NearQuery,
    PageQuery,
    SiteDetail,
    SiteId,
    SitePage,
    SnapshotQuery,
)
from watergeo.api.water_supply_models import ApiError
from watergeo.db.thames_discharge import (
    ThamesDischargeQueries,
    ThamesDischargeSiteNotFound,
    ThamesDischargeUnavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/thames-water/discharge-status",
    tags=["thames-water-discharge-status"],
    responses={503: {"model": ApiError}},
)


def queries(
    response: Response, engine: Annotated[Engine, Depends(get_database)]
) -> Iterator[ThamesDischargeQueries]:
    response.headers["Cache-Control"] = "no-store"
    try:
        yield ThamesDischargeQueries(engine)
    except ThamesDischargeSiteNotFound:
        raise HTTPException(
            404, "Discharge site not found", headers={"Cache-Control": "no-store"}
        ) from None
    except (SQLAlchemyError, ThamesDischargeUnavailable, ValidationError) as error:
        logger.warning("thames_discharge_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503, "Thames Water discharge dataset unavailable", headers={"Cache-Control": "no-store"}
        ) from None


Queries = Annotated[ThamesDischargeQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[SnapshotQuery, Query()], db: Queries) -> Dataset:
    return db.dataset(query.snapshot_id)


@router.get("/sites")
def sites(query: Annotated[PageQuery, Query()], db: Queries) -> SitePage:
    return db.sites(
        db.dataset(query.snapshot_id),
        limit=query.limit,
        after_id=query.after_id,
        alert_status=query.alert_status,
        alert_past_48_hours=query.alert_past_48_hours,
    )


@router.get("/sites/near")
def near(query: Annotated[NearQuery, Query()], db: Queries) -> SitePage:
    return db.sites(
        db.dataset(query.snapshot_id),
        limit=query.limit,
        alert_status=query.alert_status,
        alert_past_48_hours=query.alert_past_48_hours,
        point=(query.lon, query.lat, query.radius_m),
    )


@router.get("/sites/{site_id}", responses={404: {"model": ApiError}})
def site(site_id: SiteId, query: Annotated[SnapshotQuery, Query()], db: Queries) -> SiteDetail:
    dataset = db.dataset(query.snapshot_id)
    return db.site(dataset, site_id)
