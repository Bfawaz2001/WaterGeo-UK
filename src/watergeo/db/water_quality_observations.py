"""Read a versioned immutable observation retrieval using C-collated keyset paging."""

from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.water_quality_observation_models import ObservationRetrieval
from watergeo.ingestion.water_quality_observations import VERSION


def retrieval(
    engine: Engine, identity: UUID, *, limit: int, after_id: str | None
) -> ObservationRetrieval | None:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("""
            SELECT id AS retrieval_id, sampling_point_snapshot_id, sampling_point_id,
                date_from, date_to, determinand, retrieval_started_at, retrieval_completed_at,
                content_sha256, normalized_sha256, normalization_version, record_count
            FROM watergeo.water_quality_observation_retrieval
            WHERE id=:id AND normalization_version=:version
        """),
                {"id": identity, "version": VERSION},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        units = list(
            connection.execute(
                text("""
            SELECT source_fields FROM watergeo.water_quality_observation_unit
            WHERE retrieval_id=:id ORDER BY notation COLLATE "C"
        """),
                {"id": identity},
            ).scalars()
        )
        rows = list(
            connection.execute(
                text("""
            SELECT observation_id, sampling_point_id, sample_id, sampling_id,
                observed_at_text, determinand_notation, unit_notation, result_text,
                numeric_value, upper_bound, lower_bound,
                source_fields->'hasSample' AS publisher_sample
            FROM watergeo.water_quality_observation WHERE retrieval_id=:id
                AND (CAST(:after AS text) IS NULL OR observation_id COLLATE "C" > :after)
            ORDER BY observation_id COLLATE "C" LIMIT :limit
        """),
                {"id": identity, "after": after_id, "limit": limit + 1},
            ).mappings()
        )
    return ObservationRetrieval.model_validate(
        {
            **row,
            "units": units,
            "observations": rows[:limit],
            "next_after_id": rows[limit - 1]["observation_id"] if len(rows) > limit else None,
        }
    )
