"""Application factory with process liveness and dependency readiness."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import Engine

from watergeo.api.catchments import router as catchments_router
from watergeo.api.dependencies import get_database as get_database
from watergeo.api.hydrology import router as hydrology_router
from watergeo.api.hydrology_history import router as hydrology_history_router
from watergeo.api.sources import router as sources_router
from watergeo.api.water_quality import router as water_quality_router
from watergeo.api.water_quality_observations import router as water_quality_observations_router
from watergeo.api.water_supply import router as water_supply_router
from watergeo.core.config import Settings
from watergeo.core.logging import configure_logging
from watergeo.db.engine import create_database_engine, database_is_ready

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(configuration.log_level)
        engine = create_database_engine(configuration)
        app.state.database = engine
        logger.info("application_started")
        try:
            yield
        finally:
            engine.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title="WaterGeo UK",
        version="0.1.0",
        description=(
            "Independent public water-data API. Dated analytical boundaries, not legal records."
        ),
        lifespan=lifespan,
    )

    @app.get("/health", tags=["operations"])
    def health(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse()

    @app.get(
        "/ready",
        tags=["operations"],
        responses={503: {"model": ReadinessResponse, "description": "Database is not ready"}},
    )
    def ready(
        response: Response, database: Annotated[Engine, Depends(get_database)]
    ) -> ReadinessResponse:
        response.headers["Cache-Control"] = "no-store"
        if not database_is_ready(database):
            response.status_code = 503
            return ReadinessResponse(status="not_ready")
        return ReadinessResponse(status="ready")

    app.state.settings = configuration
    app.include_router(sources_router)
    app.include_router(water_quality_router)
    app.include_router(water_quality_observations_router)
    app.include_router(catchments_router)
    app.include_router(hydrology_router)
    app.include_router(hydrology_history_router)
    app.include_router(water_supply_router)
    return app
