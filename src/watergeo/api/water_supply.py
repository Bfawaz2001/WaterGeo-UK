"""Public read-only water-supply routes."""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from watergeo.api.dependencies import get_database
from watergeo.api.water_supply_models import (
    ApiError,
    AreaDetail,
    AreaFeature,
    AreaPage,
    AreaQuery,
    DatasetMetadata,
    NoQuery,
    PointQuery,
    SourceId,
)
from watergeo.db.water_supply import (
    AreaNotFound,
    DatasetUnavailable,
    GeometryTooLarge,
    WaterSupplyQueries,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/water-supply",
    tags=["water-supply"],
    responses={503: {"model": ApiError, "description": "Dataset unavailable"}},
)


class GeoJSONResponse(JSONResponse):
    media_type = "application/geo+json"


def queries(
    response: Response,
    engine: Annotated[Engine, Depends(get_database)],
) -> Iterator[WaterSupplyQueries]:
    response.headers["Cache-Control"] = "no-store"
    db = WaterSupplyQueries(engine)
    try:
        yield db
    except AreaNotFound:
        raise HTTPException(404, "Area not found", headers={"Cache-Control": "no-store"}) from None
    except GeometryTooLarge:
        raise HTTPException(
            413,
            "Geometry exceeds the 8 MiB output limit",
            headers={"Cache-Control": "no-store"},
        ) from None
    except (SQLAlchemyError, DatasetUnavailable, ValidationError) as error:
        logger.warning("water_supply_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            503,
            "Water-supply dataset unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None
    finally:
        db.close()


Queries = Annotated[WaterSupplyQueries, Depends(queries)]


@router.get("/dataset")
def dataset(query: Annotated[NoQuery, Query()], db: Queries) -> DatasetMetadata:
    """Provenance for the explicitly published Ofwat v1.5 snapshot; 503 until loaded."""
    return db.dataset()


@router.get("/areas")
def areas(query: Annotated[AreaQuery, Query()], db: Queries) -> AreaPage:
    """Metadata only, ordered by source ID. Continue with next_after_id as after_id."""
    snapshot = db.dataset()
    return db.areas(snapshot.snapshot_id, limit=query.limit, after_id=query.after_id)


# Register the literal path before the source-ID path.
@router.get("/areas/at-point")
def at_point(query: Annotated[PointQuery, Query()], db: Queries) -> AreaPage:
    """WGS84 point coverage, including boundaries. Zero or multiple matches are valid.

    Uses ST_Covers in EPSG:27700. Results are paginated without geometry.
    Coordinates outside the conservative GB processing extent (-9..3 lon,
    49..61 lat) return no matches. This is not a definitive property-supplier lookup.
    """
    snapshot = db.dataset()
    return db.areas(
        snapshot.snapshot_id,
        limit=query.limit,
        after_id=query.after_id,
        point=(query.lon, query.lat),
    )


@router.get("/areas/{source_id}", responses={404: {"model": ApiError}})
def area(source_id: SourceId, query: Annotated[NoQuery, Query()], db: Queries) -> AreaDetail:
    """Publisher labels, source notices and any reviewed transformation provenance."""
    return db.area(db.dataset().snapshot_id, source_id)


@router.get(
    "/areas/{source_id}/geometry",
    response_class=GeoJSONResponse,
    responses={404: {"model": ApiError}, 413: {"model": ApiError}},
)
def geometry(source_id: SourceId, query: Annotated[NoQuery, Query()], db: Queries) -> AreaFeature:
    """One GeoJSON Feature, WGS84 longitude/latitude, with counterclockwise shells.

    Geometry is reprojected at query time, without simplifying canonical storage.
    Four exact reviewed geometries have a hash-checked presentation-only structure
    repair (ADR 0006). Other geometries use plain reprojection. Invalid output or
    a reviewed output hash mismatch returns 503. Geometry is limited to 8 MiB.
    """
    return db.feature(db.dataset().snapshot_id, source_id)
