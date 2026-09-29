"""One bounded, parameterised search over current compatible snapshots."""

from sqlalchemy import Engine, text

from watergeo.api.search_models import SearchKind, SearchResponse, SearchResult
from watergeo.core.datasets import (
    OFWAT_WATER_SUPPLY_SHA256,
    OFWAT_WATER_SUPPLY_TRANSFORMATION,
)
from watergeo.ingestion.catchments import PLAN_VERSION as CATCHMENT_PLAN_VERSION
from watergeo.ingestion.catchments import VERSION as CATCHMENT_VERSION
from watergeo.ingestion.hydrology import VERSION as HYDROLOGY_VERSION
from watergeo.ingestion.phase15_sources import VERSION as PHASE15_VERSION
from watergeo.ingestion.stream_reservoirs import VERSION as RESERVOIR_VERSION
from watergeo.ingestion.thames_discharge import VERSION as THAMES_VERSION
from watergeo.ingestion.water_quality import VERSION as WATER_QUALITY_VERSION

SEARCH_SQL = text("""
WITH
hydrology_snapshot AS (
    SELECT id FROM watergeo.hydrology_snapshot
    WHERE normalization_version=:hydrology_version
    ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
),
rainfall_snapshot AS (
    SELECT s.id FROM watergeo.national_source_retrieval r
    JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
    WHERE s.source_key='rainfall' AND s.normalization_version=:phase15_version
    ORDER BY r.retrieval_completed_at DESC,r.id DESC LIMIT 1
),
flood_snapshot AS (
    SELECT s.id FROM watergeo.national_source_retrieval r
    JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
    WHERE s.source_key='flood-monitoring' AND s.normalization_version=:phase15_version
    ORDER BY r.retrieval_completed_at DESC,r.id DESC LIMIT 1
),
bathing_snapshot AS (
    SELECT s.id FROM watergeo.national_source_retrieval r
    JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
    WHERE s.source_key='bathing-waters' AND s.normalization_version=:phase15_version
    ORDER BY r.retrieval_completed_at DESC,r.id DESC LIMIT 1
),
water_quality_snapshot AS (
    SELECT id FROM watergeo.water_quality_snapshot
    WHERE normalization_version=:water_quality_version
    ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
),
reservoir_snapshot AS (
    SELECT id FROM watergeo.stream_reservoir_snapshot
    WHERE normalization_version=:reservoir_version
    ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
),
thames_snapshot AS (
    SELECT id FROM watergeo.thames_discharge_snapshot
    WHERE normalization_version=:thames_version
    ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
),
catchment_snapshot AS (
    SELECT id FROM watergeo.catchment_snapshot
    WHERE normalization_version=:catchment_version AND plan_version=:catchment_plan
    ORDER BY retrieval_completed_at DESC,id DESC LIMIT 1
),
supply_snapshot AS (
    SELECT id FROM watergeo.water_supply_snapshot
    WHERE source_sha256=:supply_sha256 AND transformation_version=:supply_version
    LIMIT 1
),
matches AS (
    SELECT 'hydrology'::text AS kind,h.station_id AS identity,
        COALESCE(h.labels->>0,h.station_id) AS label,'Hydrology station'::text AS context,
        'Environment Agency'::text AS publisher,h.snapshot_id,
        h.longitude,h.latitude,
        CASE WHEN lower(h.station_id)=:term THEN 0 ELSE 1 END AS match_rank
    FROM watergeo.hydrology_station h JOIN hydrology_snapshot s ON s.id=h.snapshot_id
    WHERE lower(h.station_id)=:term
       OR lower(COALESCE(h.labels->>0,'')) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'rainfall',r.station_id,COALESCE(r.display_name,'Rainfall station ' || r.station_id),
        'Rainfall gauge · publisher-reduced location','Environment Agency',r.snapshot_id,
        public.ST_X(r.geom),public.ST_Y(r.geom),
        CASE WHEN lower(r.station_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.rainfall_station r JOIN rainfall_snapshot s ON s.id=r.snapshot_id
    WHERE lower(r.station_id)=:term OR lower(COALESCE(r.display_name,'')) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'water-quality',q.sampling_point_id,COALESCE(q.pref_label,q.alt_label),
        'Water Quality sampling point','Environment Agency',q.snapshot_id,
        q.longitude,q.latitude,
        CASE WHEN lower(q.sampling_point_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.water_quality_sampling_point q
    JOIN water_quality_snapshot s ON s.id=q.snapshot_id
    WHERE lower(q.sampling_point_id)=:term
       OR lower(COALESCE(q.pref_label,q.alt_label)) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'flood-warnings',f.area_id,f.label,'Flood area · ' || f.county,
        'Environment Agency',f.snapshot_id,public.ST_X(f.centroid),public.ST_Y(f.centroid),
        CASE WHEN lower(f.area_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.flood_area f JOIN flood_snapshot s ON s.id=f.snapshot_id
    WHERE lower(f.area_id)=:term OR lower(f.label) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'bathing-waters',b.bathing_water_id,b.name,
        'Bathing water · ' || COALESCE(
            'classification ' || b.classification,
            'classification not published'
        ),
        'Environment Agency',b.snapshot_id,public.ST_X(b.geom),public.ST_Y(b.geom),
        CASE WHEN lower(b.bathing_water_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.bathing_water b JOIN bathing_snapshot s ON s.id=b.snapshot_id
    WHERE lower(b.bathing_water_id)=:term OR lower(b.name) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'reservoirs',r.reservoir_id,r.name,'Reservoir level edition',
        'Severn Trent Water',r.snapshot_id,r.longitude,r.latitude,
        CASE WHEN lower(r.reservoir_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.stream_reservoir r JOIN reservoir_snapshot s ON s.id=r.snapshot_id
    WHERE lower(r.reservoir_id)=:term OR lower(r.name) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'thames-discharge',t.site_id,t.location_name,
        'Discharge monitor · ' || t.alert_status,'Thames Water Utilities Limited',
        t.snapshot_id,public.ST_X(t.geom),public.ST_Y(t.geom),
        CASE WHEN lower(t.site_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.thames_discharge_site t JOIN thames_snapshot s ON s.id=t.snapshot_id
    WHERE lower(t.site_id)=:term OR lower(t.location_name) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'water-body',w.water_body_id,w.name,
        COALESCE(w.water_body_type || ' Water Body','Water Body'),
        'Environment Agency',w.snapshot_id,NULL::double precision,NULL::double precision,
        CASE WHEN lower(w.water_body_id)=:term THEN 0 ELSE 1 END
    FROM watergeo.catchment_water_body w JOIN catchment_snapshot s ON s.id=w.snapshot_id
    WHERE lower(w.water_body_id)=:term OR lower(w.name) LIKE :prefix ESCAPE '\\'

    UNION ALL
    SELECT 'water-supply',a.source_id::text,
        COALESCE(a.source_fields->>'COMPANY','Area ' || a.source_id::text),
        COALESCE(a.source_fields->>'AreaServed','Water-supply area'),
        'Ofwat',a.snapshot_id,NULL::double precision,NULL::double precision,
        CASE WHEN a.source_id::text=:term THEN 0 ELSE 1 END
    FROM watergeo.water_supply_area a JOIN supply_snapshot s ON s.id=a.snapshot_id
    WHERE a.source_id::text=:term
       OR lower(COALESCE(a.source_fields->>'COMPANY','')) LIKE :prefix ESCAPE '\\'
       OR lower(COALESCE(a.source_fields->>'AreaServed','')) LIKE :prefix ESCAPE '\\'
)
SELECT kind,identity,label,context,publisher,snapshot_id,longitude,latitude
FROM matches
ORDER BY match_rank,lower(label),kind,identity COLLATE "C"
LIMIT :limit
""")

AVAILABILITY_SQL = text("""
SELECT
    EXISTS(SELECT 1 FROM watergeo.hydrology_snapshot
        WHERE normalization_version=:hydrology_version) AS hydrology,
    EXISTS(SELECT 1 FROM watergeo.national_source_retrieval r
        JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
        WHERE s.source_key='rainfall' AND s.normalization_version=:phase15_version) AS rainfall,
    EXISTS(SELECT 1 FROM watergeo.national_source_retrieval r
        JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
        WHERE s.source_key='flood-monitoring'
            AND s.normalization_version=:phase15_version) AS flood,
    EXISTS(SELECT 1 FROM watergeo.national_source_retrieval r
        JOIN watergeo.national_source_snapshot s ON s.id=r.snapshot_id
        WHERE s.source_key='bathing-waters'
            AND s.normalization_version=:phase15_version) AS bathing,
    EXISTS(SELECT 1 FROM watergeo.water_quality_snapshot
        WHERE normalization_version=:water_quality_version) AS water_quality,
    EXISTS(SELECT 1 FROM watergeo.stream_reservoir_snapshot
        WHERE normalization_version=:reservoir_version) AS reservoirs,
    EXISTS(SELECT 1 FROM watergeo.thames_discharge_snapshot
        WHERE normalization_version=:thames_version) AS thames_discharge,
    EXISTS(SELECT 1 FROM watergeo.catchment_snapshot
        WHERE normalization_version=:catchment_version AND plan_version=:catchment_plan)
        AS water_body,
    EXISTS(SELECT 1 FROM watergeo.water_supply_snapshot
        WHERE source_sha256=:supply_sha256 AND transformation_version=:supply_version)
        AS water_supply
""")

KIND_COLUMNS: dict[SearchKind, str] = {
    "hydrology": "hydrology",
    "rainfall": "rainfall",
    "water-quality": "water_quality",
    "flood-warnings": "flood",
    "bathing-waters": "bathing",
    "reservoirs": "reservoirs",
    "thames-discharge": "thames_discharge",
    "water-body": "water_body",
    "water-supply": "water_supply",
}


class SearchQueries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def search(self, query: str, *, limit: int) -> SearchResponse:
        term = " ".join(query.lower().split())
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        parameters = {
            "term": term,
            "prefix": escaped + "%",
            "limit": limit + 1,
            "hydrology_version": HYDROLOGY_VERSION,
            "phase15_version": PHASE15_VERSION,
            "water_quality_version": WATER_QUALITY_VERSION,
            "reservoir_version": RESERVOIR_VERSION,
            "thames_version": THAMES_VERSION,
            "catchment_version": CATCHMENT_VERSION,
            "catchment_plan": CATCHMENT_PLAN_VERSION,
            "supply_sha256": OFWAT_WATER_SUPPLY_SHA256,
            "supply_version": OFWAT_WATER_SUPPLY_TRANSFORMATION,
        }
        with (
            self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            rows = list(connection.execute(SEARCH_SQL, parameters).mappings())
            availability = connection.execute(AVAILABILITY_SQL, parameters).mappings().one()
        available: list[SearchKind] = [
            kind for kind, column in KIND_COLUMNS.items() if availability[column]
        ]
        return SearchResponse(
            query=query,
            items=[SearchResult.model_validate(row) for row in rows[:limit]],
            truncated=len(rows) > limit,
            available_kinds=available,
            unavailable_kinds=[kind for kind in KIND_COLUMNS if kind not in available],
        )
