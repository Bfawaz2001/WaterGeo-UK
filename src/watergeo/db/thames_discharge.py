"""Snapshot-pinned queries for Thames Water discharge status."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.thames_discharge_models import AlertStatus, Dataset, SiteDetail, SitePage
from watergeo.ingestion.thames_discharge import VERSION


class ThamesDischargeUnavailable(Exception):
    pass


class ThamesDischargeSiteNotFound(Exception):
    pass


class ThamesDischargeQueries:
    def __init__(self, engine: Engine):
        self.engine = engine

    def dataset(self, snapshot_id: UUID | None = None) -> Dataset:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT id AS snapshot_id,api_version,retrieval_started_at,retrieval_completed_at,
                    content_sha256,normalized_sha256,normalization_version,site_count,
                    discharging_count,offline_count
                FROM watergeo.thames_discharge_snapshot
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
            raise ThamesDischargeUnavailable()
        return Dataset.model_validate(row)

    def sites(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after_id: str | None = None,
        alert_status: AlertStatus | None = None,
        alert_past_48_hours: bool | None = None,
        point: tuple[float, float, float] | None = None,
    ) -> SitePage:
        params: dict[str, Any] = {
            "snapshot": dataset.snapshot_id,
            "limit": limit + 1,
            "after": after_id,
            "status": alert_status,
            "recent": alert_past_48_hours,
        }
        if point is None:
            statement = text("""
                SELECT s.site_id,s.location_name,s.permit_number,s.grid_reference,s.easting,
                    s.northing,public.ST_AsGeoJSON(s.geom)::jsonb AS geometry,
                    s.receiving_watercourse,s.alert_status,s.status_changed,
                    s.alert_past_48_hours,s.most_recent_discharge_start,
                    s.most_recent_discharge_stop,NULL::double precision AS distance_m
                FROM watergeo.thames_discharge_site s
                WHERE s.snapshot_id=:snapshot
                    AND (CAST(:status AS text) IS NULL OR s.alert_status=:status)
                    AND (CAST(:recent AS boolean) IS NULL OR s.alert_past_48_hours=:recent)
                    AND (CAST(:after AS text) IS NULL OR s.site_id COLLATE "C" > :after)
                ORDER BY s.site_id COLLATE "C" LIMIT :limit
            """)
        else:
            params.update(lon=point[0], lat=point[1], radius=point[2], limit=limit)
            statement = text("""
                SELECT s.site_id,s.location_name,s.permit_number,s.grid_reference,s.easting,
                    s.northing,public.ST_AsGeoJSON(s.geom)::jsonb AS geometry,
                    s.receiving_watercourse,s.alert_status,s.status_changed,
                    s.alert_past_48_hours,s.most_recent_discharge_start,
                    s.most_recent_discharge_stop,
                    public.ST_Distance(s.geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)
                            ::public.geography) AS distance_m
                FROM watergeo.thames_discharge_site s
                WHERE s.snapshot_id=:snapshot
                    AND (CAST(:status AS text) IS NULL OR s.alert_status=:status)
                    AND (CAST(:recent AS boolean) IS NULL OR s.alert_past_48_hours=:recent)
                    AND public.ST_DWithin(s.geom::public.geography,
                        public.ST_SetSRID(public.ST_MakePoint(:lon,:lat),4326)
                            ::public.geography,:radius)
                ORDER BY distance_m,s.site_id COLLATE "C" LIMIT :limit
            """)
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())
        return SitePage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": rows[limit - 1]["site_id"]
                if point is None and len(rows) > limit
                else None,
            }
        )

    def site(self, dataset: Dataset, identity: str) -> SiteDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT site_id,location_name,permit_number,grid_reference,easting,northing,
                    public.ST_AsGeoJSON(geom)::jsonb AS geometry,receiving_watercourse,
                    alert_status,status_changed,alert_past_48_hours,
                    most_recent_discharge_start,most_recent_discharge_stop,
                    NULL::double precision AS distance_m
                FROM watergeo.thames_discharge_site
                WHERE snapshot_id=:snapshot AND site_id=:site
            """),
                    {"snapshot": dataset.snapshot_id, "site": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ThamesDischargeSiteNotFound()
        return SiteDetail.model_validate({**row, "dataset": dataset})
