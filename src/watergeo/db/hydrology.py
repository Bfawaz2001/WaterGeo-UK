"""Snapshot-pinned, read-only bounded hydrology queries."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.hydrology_models import Dataset, StationDetail, StationPage
from watergeo.ingestion.hydrology import ATTRIBUTION, LICENCE, MAX_MEASURES, ROOT, VERSION


class HydrologyUnavailable(Exception):
    """No compatible snapshot, or stored response contract failure."""


class StationNotFound(Exception):
    """Station does not exist in the selected snapshot."""


class HydrologyQueries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def dataset(self, snapshot_id: UUID | None = None) -> Dataset:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT * FROM watergeo.hydrology_snapshot
                WHERE normalization_version = :version AND (CAST(:id AS uuid) IS NULL OR id = :id)
                ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1
            """),
                    {"version": VERSION, "id": snapshot_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise HydrologyUnavailable()
        return Dataset.model_validate(
            {
                **row,
                "snapshot_id": row["id"],
                "publisher": "Environment Agency",
                "source_api": ROOT,
                "documentation_url": ROOT + "/doc/reference",
                "licence": "Open Government Licence v3",
                "licence_url": LICENCE,
                "attribution": ATTRIBUTION,
                "geographic_coverage": "England",
                "scope": ["waterLevel", "waterFlow"],
                "request_manifest": row["manifest"],
                "freshness_caveat": (
                    "Latest available observations may be old or missing. "
                    "Retrieval time is not observation time; "
                    "pages are not a publisher-atomic release."
                ),
            }
        )

    def stations(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after_id: str | None = None,
        point: tuple[float, float, float] | None = None,
    ) -> StationPage:
        params: dict[str, Any] = {"id": dataset.snapshot_id, "limit": limit + 1, "after": after_id}
        if point is None:
            statement = text("""
                SELECT station_id, source_uri, labels, latitude, longitude,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry,
                    CASE WHEN geom IS NULL THEN 'unavailable' ELSE 'available' END AS
                    location_status
                FROM watergeo.hydrology_station WHERE snapshot_id = :id
                    AND (CAST(:after AS text) IS NULL OR station_id COLLATE "C" > :after)
                ORDER BY station_id COLLATE "C" LIMIT :limit
            """)
        else:
            params.update(lon=point[0], lat=point[1], radius=point[2], limit=limit)
            statement = text("""
                SELECT station_id, source_uri, labels, latitude, longitude,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry, 'available' AS location_status,
                    public.ST_Distance(geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)
                        ::public.geography) AS distance_m
                FROM watergeo.hydrology_station WHERE snapshot_id = :id AND geom IS NOT NULL
                    AND public.ST_DWithin(geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)
                        ::public.geography, :radius)
                ORDER BY distance_m, station_id COLLATE "C" LIMIT :limit
            """)
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())
        return StationPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": rows[limit - 1]["station_id"]
                if point is None and len(rows) > limit
                else None,
                "spatial_exclusion_note": (
                    "Stations without locations cannot be included in distance "
                    "search; see dataset spatial completeness counts."
                )
                if point
                else None,
            }
        )

    def station(self, dataset: Dataset, station_id: str) -> StationDetail:
        params = {"id": dataset.snapshot_id, "station": station_id, "limit": MAX_MEASURES + 1}
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT *, public.ST_AsGeoJSON(geom)::jsonb AS geometry,
                    CASE WHEN geom IS NULL THEN 'unavailable' ELSE 'available' END AS
                    location_status
                FROM watergeo.hydrology_station WHERE snapshot_id = :id AND station_id = :station
            """),
                    params,
                )
                .mappings()
                .first()
            )
            if row is None:
                raise StationNotFound()
            measures = list(
                connection.execute(
                    text("""
                SELECT m.*, CASE WHEN o.measure_id IS NULL THEN NULL ELSE jsonb_build_object(
                    'observed_at', o.observed_at, 'value', o.value, 'source_fields',
                    o.source_fields)
                    END AS latest_observation
                FROM watergeo.hydrology_measure m LEFT JOIN watergeo.hydrology_latest_observation o
                    ON o.snapshot_id = m.snapshot_id AND o.measure_id = m.measure_id
                WHERE m.snapshot_id = :id AND m.station_id = :station
                ORDER BY m.measure_id COLLATE "C" LIMIT :limit
            """),
                    params,
                ).mappings()
            )
        if len(measures) > MAX_MEASURES:
            raise HydrologyUnavailable()
        return StationDetail.model_validate({**row, "dataset": dataset, "measures": measures})
