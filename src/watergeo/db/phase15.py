"""Read-only queries for Phase 15 national products."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.phase15_models import Dataset, Detail, Page
from watergeo.ingestion.phase15_sources import (
    BATHING_ROOT,
    EA_LICENCE,
    FLOOD_ROOT,
    OFWAT_WCPR_URL,
    VERSION,
)

PRODUCTS = {
    "rainfall": {
        "publisher": "Environment Agency",
        "source_url": f"{FLOOD_ROOT}/id/stations?parameter=rainfall",
        "attribution": (
            "This uses Environment Agency rainfall data from the real-time data API (Beta)."
        ),
        "caveat": (
            "Latest accepted WaterGeo retrieval. Rainfall stations may be unnamed and locations "
            "are publisher-reduced to a 100 m grid; WaterGeo does not infer more precise locations."
        ),
    },
    "flood-monitoring": {
        "publisher": "Environment Agency",
        "source_url": f"{FLOOD_ROOT}/id/floods",
        "attribution": (
            "This uses Environment Agency flood data from the real-time data API (Beta)."
        ),
        "caveat": (
            "WaterGeo is not an emergency warning service. This is the latest accepted WaterGeo "
            "retrieval; use the official Environment Agency flood service for safety decisions."
        ),
    },
    "bathing-waters": {
        "publisher": "Environment Agency",
        "source_url": BATHING_ROOT,
        "attribution": "Contains Environment Agency bathing-water data licensed under OGL 3.0.",
        "caveat": (
            "Classification, sample context and publisher advice are separate facts. WaterGeo "
            "does not make a safe-to-swim judgement."
        ),
    },
    "company-performance": {
        "publisher": "Ofwat",
        "source_url": OFWAT_WCPR_URL,
        "attribution": "Contains Ofwat company-performance data licensed under OGL 3.0.",
        "caveat": (
            "Values retain their publisher reporting period, unit and definition. Missing and "
            "not-applicable values are distinct from numeric zero."
        ),
    },
}


class Phase15Unavailable(RuntimeError):
    pass


class Phase15NotFound(LookupError):
    pass


class Phase15Queries:
    def __init__(self, engine: Engine):
        self.engine = engine

    def dataset(self, source: str, snapshot_id: UUID | None = None) -> Dataset:
        if source not in PRODUCTS:
            raise Phase15Unavailable
        clause = "s.id=:id" if snapshot_id else "s.source_key=:source"
        parameters: dict[str, Any] = {"id": snapshot_id} if snapshot_id else {"source": source}
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(f"""
                        SELECT s.*,r.id AS retrieval_id,
                            r.retrieval_started_at AS accepted_retrieval_started_at,
                            r.retrieval_completed_at AS accepted_retrieval_completed_at
                        FROM watergeo.national_source_snapshot s
                        JOIN watergeo.national_source_retrieval r ON r.snapshot_id=s.id
                        WHERE {clause}
                            AND s.normalization_version=:version
                        ORDER BY r.retrieval_completed_at DESC,r.id DESC LIMIT 1
                    """),  # noqa: S608
                    {**parameters, "version": VERSION},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["source_key"] != source:
            raise Phase15Unavailable
        metadata = PRODUCTS[source]
        return Dataset(
            snapshot_id=row["id"],
            retrieval_id=row["retrieval_id"],
            source=source,
            publisher=metadata["publisher"],
            source_url=metadata["source_url"],
            licence="Open Government Licence 3.0",
            licence_url=EA_LICENCE,
            attribution=metadata["attribution"],
            retrieval_started_at=row["accepted_retrieval_started_at"],
            retrieval_completed_at=row["accepted_retrieval_completed_at"],
            content_sha256=row["content_sha256"],
            normalized_sha256=row["normalized_sha256"],
            normalization_version=row["normalization_version"],
            entity_count=row["entity_count"],
            secondary_count=row["secondary_count"],
            skipped_count=row["skipped_count"],
            caveat=metadata["caveat"],
        )

    def rainfall(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after: str | None,
        near: tuple[float, float, float] | None,
    ) -> Page:
        point = near or (0.0, 0.0, 1.0)
        parameters: dict[str, Any] = {
            "snapshot": dataset.snapshot_id,
            "after": after,
            "limit": limit + 1,
            "near": near is not None,
            "lon": point[0],
            "lat": point[1],
            "radius": point[2],
        }
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT station_id,publisher_uri,display_name,
                    public.ST_Y(geom) AS latitude,public.ST_X(geom) AS longitude,
                    grid_reference,latest_observed_at,latest_value_mm,latest_value,
                    latest_unit,latest_period_seconds,
                    CASE WHEN CAST(:near AS boolean) THEN public.ST_Distance(
                        geom::public.geography,public.ST_SetSRID(
                            public.ST_MakePoint(:lon,:lat),4326)::public.geography)
                    END AS distance_m
                FROM watergeo.rainfall_station
                WHERE snapshot_id=:snapshot
                    AND (CAST(:after AS text) IS NULL OR station_id>:after)
                    AND (NOT CAST(:near AS boolean) OR public.ST_DWithin(
                        geom::public.geography,public.ST_SetSRID(
                            public.ST_MakePoint(:lon,:lat),4326)::public.geography,:radius))
                ORDER BY station_id COLLATE "C" LIMIT :limit
            """),
                    parameters,
                )
                .mappings()
                .all()
            )
        items = [dict(row) for row in rows[:limit]]
        return Page(
            dataset=dataset,
            items=items,
            next_after_id=items[-1]["station_id"] if len(rows) > limit else None,
        )

    def bathing(
        self,
        dataset: Dataset,
        *,
        limit: int,
        after: str | None,
        near: tuple[float, float, float] | None,
    ) -> Page:
        point = near or (0.0, 0.0, 1.0)
        parameters: dict[str, Any] = {
            "snapshot": dataset.snapshot_id,
            "after": after,
            "limit": limit + 1,
            "near": near is not None,
            "lon": point[0],
            "lat": point[1],
            "radius": point[2],
        }
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT bathing_water_id,publisher_uri,name,public.ST_Y(geom) AS latitude,
                    public.ST_X(geom) AS longitude,classification,assessment_year,
                    latest_sample_uri,latest_risk_prediction,
                    CASE WHEN CAST(:near AS boolean) THEN public.ST_Distance(
                        geom::public.geography,public.ST_SetSRID(
                            public.ST_MakePoint(:lon,:lat),4326)::public.geography)
                    END AS distance_m
                FROM watergeo.bathing_water
                WHERE snapshot_id=:snapshot
                    AND (CAST(:after AS text) IS NULL OR bathing_water_id>:after)
                    AND (NOT CAST(:near AS boolean) OR public.ST_DWithin(
                        geom::public.geography,public.ST_SetSRID(
                            public.ST_MakePoint(:lon,:lat),4326)::public.geography,:radius))
                ORDER BY bathing_water_id COLLATE "C" LIMIT :limit
            """),
                    parameters,
                )
                .mappings()
                .all()
            )
        items = [dict(row) for row in rows[:limit]]
        return Page(
            dataset=dataset,
            items=items,
            next_after_id=items[-1]["bathing_water_id"] if len(rows) > limit else None,
        )

    def flood_areas(self, dataset: Dataset, *, warnings_only: bool = False) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT a.area_id,a.label,a.description,a.county,a.river_or_sea,
                    public.ST_AsGeoJSON(a.geom)::jsonb AS geometry,a.geometry_policy,
                    w.warning_id,w.severity,
                    w.severity_level,w.message,w.time_raised,w.time_message_changed,
                    w.time_severity_changed
                FROM watergeo.flood_area a
                LEFT JOIN watergeo.flood_warning w USING (snapshot_id,area_id)
                WHERE a.snapshot_id=:snapshot AND (NOT :warnings_only OR w.warning_id IS NOT NULL)
                ORDER BY a.area_id COLLATE "C"
            """),
                    {"snapshot": dataset.snapshot_id, "warnings_only": warnings_only},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def companies(self, dataset: Dataset) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT company_id,company_name,boundary_company_acronym
                FROM watergeo.company_performance_company WHERE snapshot_id=:snapshot
                ORDER BY company_id COLLATE "C"
            """),
                    {"snapshot": dataset.snapshot_id},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def measures(
        self, dataset: Dataset, company_id: str, *, period: str | None, measure: str | None
    ) -> Detail:
        with self.engine.connect() as connection:
            company = (
                connection.execute(
                    text("""
                SELECT company_id,company_name,boundary_company_acronym
                FROM watergeo.company_performance_company
                WHERE snapshot_id=:snapshot AND company_id=:company
            """),
                    {"snapshot": dataset.snapshot_id, "company": company_id},
                )
                .mappings()
                .one_or_none()
            )
            if company is None:
                raise Phase15NotFound
            rows = (
                connection.execute(
                    text("""
                SELECT reporting_period,measure_code,measure_name,value,value_state,unit,
                    definition,publication
                FROM watergeo.company_performance_measure
                WHERE snapshot_id=:snapshot AND company_id=:company
                    AND (CAST(:period AS text) IS NULL OR reporting_period=:period)
                    AND (CAST(:measure AS text) IS NULL OR measure_code=:measure)
                ORDER BY measure_code COLLATE "C",reporting_period COLLATE "C"
            """),
                    {
                        "snapshot": dataset.snapshot_id,
                        "company": company_id,
                        "period": period,
                        "measure": measure,
                    },
                )
                .mappings()
                .all()
            )
        return Detail(
            dataset=dataset, item={**dict(company), "measures": [dict(row) for row in rows]}
        )

    def detail(self, source: str, dataset: Dataset, identity: str) -> Detail:
        if source == "rainfall":
            statement = text("""
                SELECT station_id,publisher_uri,display_name,public.ST_Y(geom) AS latitude,
                    public.ST_X(geom) AS longitude,grid_reference,latest_observed_at,
                    latest_value_mm,latest_value,latest_unit,latest_period_seconds
                FROM watergeo.rainfall_station
                WHERE snapshot_id=:snapshot AND station_id=:identity
            """)
        else:
            statement = text("""
                SELECT bathing_water_id,publisher_uri,name,public.ST_Y(geom) AS latitude,
                    public.ST_X(geom) AS longitude,classification,assessment_year,
                    latest_sample_uri,latest_risk_prediction
                FROM watergeo.bathing_water
                WHERE snapshot_id=:snapshot AND bathing_water_id=:identity
            """)
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    statement, {"snapshot": dataset.snapshot_id, "identity": identity}
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise Phase15NotFound
        return Detail(dataset=dataset, item=dict(row))
