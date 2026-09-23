"""Snapshot-pinned read queries for Severn Trent reservoir levels."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.stream_reservoir_models import (
    Dataset,
    ReadingPage,
    ReservoirDetail,
    ReservoirPage,
)
from watergeo.ingestion.stream_reservoirs import VERSION


class StreamReservoirUnavailable(Exception):
    pass


class ReservoirNotFound(Exception):
    pass


class StreamReservoirQueries:
    def __init__(self, engine: Engine):
        self.engine = engine

    def dataset(self, snapshot_id: UUID | None = None) -> Dataset:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT id AS snapshot_id,source_item_created_at,
                            source_item_modified_at,retrieval_started_at,retrieval_completed_at,
                            content_sha256,normalized_sha256,normalization_version,
                            reservoir_count,reading_count
                        FROM watergeo.stream_reservoir_snapshot
                        WHERE normalization_version=:version
                            AND (CAST(:id AS uuid) IS NULL OR id=:id)
                        ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
                    """),
                    {"version": VERSION, "id": snapshot_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StreamReservoirUnavailable()
        return Dataset.model_validate(row)

    def reservoirs(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after_id: str | None = None,
        point: tuple[float, float, float] | None = None,
    ) -> ReservoirPage:
        params: dict[str, Any] = {
            "snapshot": dataset.snapshot_id,
            "limit": limit + 1,
            "after": after_id,
        }
        if point is None:
            statement = text("""
                SELECT r.reservoir_id,r.name,r.latitude,r.longitude,
                    public.ST_AsGeoJSON(r.geom)::jsonb AS geometry,r.capacity,r.capacity_unit,
                    NULL::double precision AS distance_m,
                    CASE WHEN latest.observed_at IS NULL THEN NULL ELSE jsonb_build_object(
                        'observed_at',latest.observed_at,'current_level',latest.current_level,
                        'current_level_unit',latest.current_level_unit,
                        'current_percentage',latest.current_percentage) END AS latest_reading
                FROM watergeo.stream_reservoir r
                LEFT JOIN LATERAL (
                    SELECT observed_at,current_level,current_level_unit,current_percentage
                    FROM watergeo.stream_reservoir_level l
                    WHERE l.snapshot_id=r.snapshot_id AND l.reservoir_id=r.reservoir_id
                    ORDER BY observed_at DESC LIMIT 1
                ) latest ON true
                WHERE r.snapshot_id=:snapshot AND (CAST(:after AS text) IS NULL
                    OR r.reservoir_id COLLATE "C" > :after)
                ORDER BY r.reservoir_id COLLATE "C" LIMIT :limit
            """)
        else:
            params.update(lon=point[0], lat=point[1], radius=point[2], limit=limit)
            statement = text("""
                SELECT r.reservoir_id,r.name,r.latitude,r.longitude,
                    public.ST_AsGeoJSON(r.geom)::jsonb AS geometry,r.capacity,r.capacity_unit,
                    public.ST_Distance(r.geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)::public.geography)
                        AS distance_m,
                    CASE WHEN latest.observed_at IS NULL THEN NULL ELSE jsonb_build_object(
                        'observed_at',latest.observed_at,'current_level',latest.current_level,
                        'current_level_unit',latest.current_level_unit,
                        'current_percentage',latest.current_percentage) END AS latest_reading
                FROM watergeo.stream_reservoir r
                LEFT JOIN LATERAL (
                    SELECT observed_at,current_level,current_level_unit,current_percentage
                    FROM watergeo.stream_reservoir_level l
                    WHERE l.snapshot_id=r.snapshot_id AND l.reservoir_id=r.reservoir_id
                    ORDER BY observed_at DESC LIMIT 1
                ) latest ON true
                WHERE r.snapshot_id=:snapshot AND public.ST_DWithin(r.geom::public.geography,
                    public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)::public.geography,
                    :radius)
                ORDER BY distance_m,r.reservoir_id COLLATE "C" LIMIT :limit
            """)
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())
        return ReservoirPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": rows[limit - 1]["reservoir_id"]
                if point is None and len(rows) > limit
                else None,
            }
        )

    def reservoir(self, dataset: Dataset, identity: str) -> ReservoirDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT r.reservoir_id,r.name,r.latitude,r.longitude,
                            public.ST_AsGeoJSON(r.geom)::jsonb AS geometry,
                            r.capacity,r.capacity_unit,NULL::double precision AS distance_m,
                            CASE WHEN latest.observed_at IS NULL THEN NULL ELSE jsonb_build_object(
                                'observed_at',latest.observed_at,
                                'current_level',latest.current_level,
                                'current_level_unit',latest.current_level_unit,
                                'current_percentage',latest.current_percentage)
                            END AS latest_reading
                        FROM watergeo.stream_reservoir r
                        LEFT JOIN LATERAL (
                            SELECT observed_at,current_level,current_level_unit,current_percentage
                            FROM watergeo.stream_reservoir_level l
                            WHERE l.snapshot_id=r.snapshot_id
                                AND l.reservoir_id=r.reservoir_id
                            ORDER BY observed_at DESC LIMIT 1
                        ) latest ON true
                        WHERE r.snapshot_id=:snapshot AND r.reservoir_id=:reservoir
                    """),
                    {"snapshot": dataset.snapshot_id, "reservoir": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ReservoirNotFound()
        return ReservoirDetail.model_validate({**row, "dataset": dataset})

    def readings(
        self,
        dataset: Dataset,
        identity: str,
        *,
        limit: int,
        after: datetime | None,
    ) -> ReadingPage:
        reservoir = self.reservoir(dataset, identity)
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    text("""
                        SELECT observed_at,current_level,current_level_unit,current_percentage
                        FROM watergeo.stream_reservoir_level
                        WHERE snapshot_id=:snapshot AND reservoir_id=:reservoir
                            AND (CAST(:after AS timestamptz) IS NULL OR observed_at>:after)
                        ORDER BY observed_at LIMIT :limit
                    """),
                    {
                        "snapshot": dataset.snapshot_id,
                        "reservoir": identity,
                        "after": after,
                        "limit": limit + 1,
                    },
                ).mappings()
            )
        return ReadingPage.model_validate(
            {
                "dataset": dataset,
                "reservoir": reservoir,
                "items": rows[:limit],
                "next_after": rows[limit - 1]["observed_at"] if len(rows) > limit else None,
            }
        )
