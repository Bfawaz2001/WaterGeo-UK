"""Read-only queries for bounded hydrology history retrievals."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text


class InvalidHistoryCursor(ValueError):
    """Discovery cursor does not belong to the requested measure."""


def list_history_retrievals(
    engine: Engine, measure_id: str, *, limit: int, after_id: UUID | None
) -> tuple[list[dict[str, Any]], UUID | None]:
    """Use the existing measure/latest index; never join history to a new snapshot."""
    with engine.connect() as connection:
        after_time = None
        if after_id is not None:
            after_time = connection.execute(
                text("""
                    SELECT retrieval_completed_at
                    FROM watergeo.hydrology_history_retrieval
                    WHERE id = :id AND measure_id = :measure_id
                """),
                {"id": after_id, "measure_id": measure_id},
            ).scalar_one_or_none()
            if after_time is None:
                raise InvalidHistoryCursor
        rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    SELECT id AS retrieval_id, measure_id, requested_from, requested_to,
                           retrieval_started_at, retrieval_completed_at, record_count,
                           content_sha256, normalized_sha256, normalization_version
                    FROM watergeo.hydrology_history_retrieval
                    WHERE measure_id = :measure_id
                      AND (CAST(:after_time AS timestamptz) IS NULL OR
                           (retrieval_completed_at, id) <
                           (CAST(:after_time AS timestamptz), CAST(:after_id AS uuid)))
                    ORDER BY retrieval_completed_at DESC, id DESC
                    LIMIT :limit
                """),
                {
                    "measure_id": measure_id,
                    "after_time": after_time,
                    "after_id": after_id,
                    "limit": limit + 1,
                },
            ).mappings()
        ]
    page = rows[:limit]
    return page, page[-1]["retrieval_id"] if len(rows) > limit else None


def get_history_retrieval(
    engine: Engine,
    retrieval_id: UUID,
) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        measure_id,
                        requested_from,
                        requested_to,
                        retrieval_started_at,
                        retrieval_completed_at,
                        content_sha256,
                        normalized_sha256,
                        normalization_version,
                        record_count
                    FROM watergeo.hydrology_history_retrieval
                    WHERE id = :id
                """),
                {"id": retrieval_id},
            )
            .mappings()
            .first()
        )

        return dict(row) if row else None


def list_history_observations(
    engine: Engine,
    retrieval_id: UUID,
    *,
    limit: int,
    after: datetime | None,
) -> tuple[list[dict[str, Any]], str | None]:
    params = {
        "id": retrieval_id,
        "limit": limit + 1,
        "after": after,
    }

    with engine.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    SELECT
                        observed_at,
                        value,
                        source_fields
                    FROM watergeo.hydrology_historical_observation
                    WHERE retrieval_id = :id
                      AND (
                          CAST(:after AS timestamptz) IS NULL
                          OR observed_at > CAST(:after AS timestamptz)
                      )
                    ORDER BY observed_at ASC
                    LIMIT :limit
                """),
                params,
            ).mappings()
        ]

    has_more = len(rows) > limit
    page = rows[:limit]

    next_after = None
    if has_more and page:
        next_after = page[-1]["observed_at"].isoformat()

    return page, next_after
