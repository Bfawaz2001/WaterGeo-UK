"""Read-only sampling-point metadata and bounded WGS84 geography queries."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.water_quality_models import Dataset, SamplingPointDetail, SamplingPointPage
from watergeo.ingestion.water_quality import VERSION


class WaterQualityUnavailable(Exception):
    pass


class SamplingPointNotFound(Exception):
    pass


class WaterQualityQueries:
    def __init__(self, engine: Engine):
        self.engine = engine

    def dataset(self, snapshot_id: UUID | None = None) -> Dataset:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT id AS snapshot_id, content_sha256, normalized_sha256,
                    normalization_version, retrieval_started_at, retrieval_completed_at,
                    sampling_point_count, sampling_point_with_location_count,
                    sampling_point_without_location_count
                FROM watergeo.water_quality_snapshot WHERE normalization_version=:version
                    AND (CAST(:id AS uuid) IS NULL OR id=:id)
                ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1
            """),
                    {"version": VERSION, "id": snapshot_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise WaterQualityUnavailable()
        return Dataset.model_validate(row)

    def points(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after_id: str | None = None,
        point: tuple[float, float, float] | None = None,
    ) -> SamplingPointPage:
        params: dict[str, Any] = {"id": dataset.snapshot_id, "limit": limit + 1, "after": after_id}
        if point is None:
            statement = text("""
                SELECT sampling_point_id, source_uri, alt_label, pref_label, latitude, longitude,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry,
                    CASE WHEN geom IS NULL THEN 'unavailable' ELSE 'available' END
                        AS location_status
                FROM watergeo.water_quality_sampling_point WHERE snapshot_id=:id
                    AND (CAST(:after AS text) IS NULL OR sampling_point_id COLLATE "C" > :after)
                ORDER BY sampling_point_id COLLATE "C" LIMIT :limit
            """)
        else:
            params.update(lon=point[0], lat=point[1], radius=point[2], limit=limit)
            statement = text("""
                SELECT sampling_point_id, source_uri, alt_label, pref_label, latitude, longitude,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry, 'available' AS location_status,
                    public.ST_Distance(geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)::public.geography)
                        AS distance_m
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id=:id AND geom IS NOT NULL
                    AND public.ST_DWithin(geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)::public.geography,
                        :radius)
                ORDER BY distance_m, sampling_point_id COLLATE "C" LIMIT :limit
            """)
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())
        return SamplingPointPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": rows[limit - 1]["sampling_point_id"]
                if point is None and len(rows) > limit
                else None,
                "spatial_exclusion_note": (
                    "Unlocated sampling points are excluded from distance search; "
                    "see dataset counts."
                )
                if point
                else None,
            }
        )

    def point(self, dataset: Dataset, identity: str) -> SamplingPointDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT sampling_point_id, source_uri, alt_label, pref_label, latitude, longitude,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry,
                    CASE WHEN geom IS NULL THEN 'unavailable' ELSE 'available' END
                        AS location_status,
                    jsonb_build_object('status', status, 'sampling_point_type', sampling_point_type,
                        'region', region, 'area', area, 'sub_area', sub_area) AS publisher_metadata
                FROM watergeo.water_quality_sampling_point
                WHERE snapshot_id=:id AND sampling_point_id=:point
            """),
                    {"id": dataset.snapshot_id, "point": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SamplingPointNotFound()
        return SamplingPointDetail.model_validate({**row, "dataset": dataset})
