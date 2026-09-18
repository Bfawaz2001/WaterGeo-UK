"""Bounded, parameterised queries for one explicitly published dataset identity."""

from uuid import UUID

from sqlalchemy import Connection, Engine, text

from watergeo.api.water_supply_models import (
    AreaDetail,
    AreaFeature,
    AreaPage,
    AreaSummary,
    DatasetMetadata,
    MultiPolygon,
    TransformationMetadata,
)
from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION

MAX_GEOMETRY_BYTES = 8 * 1024 * 1024


class DatasetUnavailable(Exception):
    """The published snapshot is absent or cannot be represented safely."""


class AreaNotFound(Exception):
    """No area in the published snapshot has this identifier."""


class GeometryTooLarge(Exception):
    """A single geometry exceeds the documented output bound."""


# These SQL fragments contain only developer-owned identifiers and literals.
# Every HTTP value and dataset selector is passed as a bound parameter.
SUMMARY_COLUMNS = """
    a.source_id,
    a.source_fields->>'AreaServed' AS area_served,
    a.source_fields->>'COMPANY' AS company,
    a.source_fields->>'Acronym' AS company_acronym,
    a.source_fields->>'CoType' AS company_type,
    a.source_fields->>'AreaType' AS area_type,
    a.source_fields->>'Version' AS source_version,
    a.source_fields->>'LastUpdate' AS source_last_update,
    a.source_fields->>'WARNINGS' AS warnings,
    (t.source_id IS NOT NULL) AS transformed
"""
AREA_TABLES = """
    FROM watergeo.water_supply_area a
    LEFT JOIN watergeo.water_supply_area_transformation t
      ON t.snapshot_id = a.snapshot_id AND t.source_id = a.source_id
"""
POINT_PREDICATE = """
    AND public.ST_Covers(a.geom,
        public.ST_Transform(public.ST_SetSRID(public.ST_MakePoint(:lon, :lat), 4326), 27700))
"""
LIST_SQL = text(
    "SELECT "
    + SUMMARY_COLUMNS
    + AREA_TABLES
    + " WHERE a.snapshot_id = :snapshot_id AND a.source_id > :after_id"
    + " ORDER BY a.source_id LIMIT :limit"
)
POINT_SQL = text(
    "SELECT "
    + SUMMARY_COLUMNS
    + AREA_TABLES
    + " WHERE a.snapshot_id = :snapshot_id AND a.source_id > :after_id"
    + POINT_PREDICATE
    + " ORDER BY a.source_id LIMIT :limit"
)
DETAIL_SQL = text(
    "SELECT "
    + SUMMARY_COLUMNS
    + """,
        a.snapshot_id,
        a.source_fields->>'Licence' AS licence_statement,
        a.source_fields->>'Provenance' AS source_provenance,
        a.source_fields->>'Disclaimer' AS disclaimer,
        a.source_fields->>'Disclaim2' AS premises_disclaimer,
        a.source_fields->>'Disclaim3' AS coastline_disclaimer,
        CASE WHEN t.source_id IS NOT NULL THEN jsonb_build_object(
            'transformation_id', t.transformation_id, 'method', t.method,
            'keep_collapsed', t.keep_collapsed, 'shapely_version', t.shapely_version,
            'geos_version', t.geos_version, 'invalid_reason', t.invalid_reason,
            'source_decoded_wkb_sha256', t.source_decoded_wkb_sha256,
            'canonical_wkb_sha256', t.canonical_wkb_sha256,
            'review_status', t.review_status, 'review_reason', t.review_reason,
            'review_reference', t.review_reference, 'transformed_at', t.transformed_at
        ) END AS transformation
    """
    + AREA_TABLES
    + " WHERE a.snapshot_id = :snapshot_id AND a.source_id = :source_id"
)
GEOMETRY_SQL = text("""
    WITH output AS MATERIALIZED (
        SELECT public.ST_AsGeoJSON(
            public.ST_ForcePolygonCCW(public.ST_Transform(geom, 4326)), 15, 0
        ) AS geojson
        FROM watergeo.water_supply_area
        WHERE snapshot_id = :snapshot_id AND source_id = :source_id
    )
    SELECT octet_length(geojson) AS byte_count,
           CASE WHEN octet_length(geojson) <= :max_bytes THEN geojson END AS geojson,
           CASE WHEN octet_length(geojson) <= :max_bytes
                THEN public.ST_IsValid(public.ST_GeomFromGeoJSON(geojson), 0)
                ELSE false END AS valid
    FROM output
""")


class WaterSupplyQueries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._connection: Connection | None = None

    @property
    def connection(self) -> Connection:
        # Connect only when a validated request actually runs a query.
        if self._connection is None:
            self._connection = self.engine.connect()
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()

    def dataset(self) -> DatasetMetadata:
        row = (
            self.connection.execute(
                text("""
                SELECT s.id AS snapshot_id, s.source_sha256, s.source_url, s.source_bytes,
                       s.retrieved_at, s.ingested_at, s.publisher, s.distributor,
                       s.licence_name, s.licence_version, s.licence_url, s.attribution,
                       s.transformation_version,
                       (SELECT count(*) FROM watergeo.water_supply_area a
                        WHERE a.snapshot_id = s.id) AS area_count,
                       (SELECT count(*) FROM watergeo.water_supply_area_transformation t
                        WHERE t.snapshot_id = s.id) AS transformed_area_count
                FROM watergeo.water_supply_snapshot s
                WHERE s.source_sha256 = :sha256 AND s.transformation_version = :version
            """),
                {"sha256": OFWAT_WATER_SUPPLY_SHA256, "version": OFWAT_WATER_SUPPLY_TRANSFORMATION},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatasetUnavailable
        return DatasetMetadata.model_validate(dict(row))

    def areas(
        self,
        snapshot_id: UUID,
        *,
        limit: int,
        after_id: int,
        point: tuple[float, float] | None = None,
    ) -> AreaPage:
        parameters: dict[str, object] = {
            "snapshot_id": snapshot_id,
            "after_id": after_id,
            "limit": limit + 1,
        }
        if point is not None:
            lon, lat = point
            # Conservative processing extent around GB: avoid projecting poles and
            # other distant coordinates into British National Grid.
            if not (-9 <= lon <= 3 and 49 <= lat <= 61):
                return AreaPage(snapshot_id=snapshot_id, items=[], next_after_id=None)
            parameters.update(lon=lon, lat=lat)
        rows = (
            self.connection.execute(POINT_SQL if point is not None else LIST_SQL, parameters)
            .mappings()
            .all()
        )
        items = [AreaSummary.model_validate(dict(row)) for row in rows[:limit]]
        return AreaPage(
            snapshot_id=snapshot_id,
            items=items,
            next_after_id=items[-1].source_id if len(rows) > limit else None,
        )

    def area(self, snapshot_id: UUID, source_id: int) -> AreaDetail:
        row = (
            self.connection.execute(
                DETAIL_SQL, {"snapshot_id": snapshot_id, "source_id": source_id}
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AreaNotFound
        values = dict(row)
        if values["transformation"] is not None:
            values["transformation"] = TransformationMetadata.model_validate(
                values["transformation"]
            )
        return AreaDetail.model_validate(
            {
                **values,
                "geometry_url": f"/v1/water-supply/areas/{source_id}/geometry",
            }
        )

    def feature(self, snapshot_id: UUID, source_id: int) -> AreaFeature:
        properties = self.area(snapshot_id, source_id)
        row = (
            self.connection.execute(
                GEOMETRY_SQL,
                {
                    "snapshot_id": snapshot_id,
                    "source_id": source_id,
                    "max_bytes": MAX_GEOMETRY_BYTES,
                },
            )
            .mappings()
            .one()
        )
        if row["byte_count"] > MAX_GEOMETRY_BYTES:
            raise GeometryTooLarge
        if not row["valid"]:
            raise DatasetUnavailable
        return AreaFeature(
            id=source_id,
            properties=properties,
            geometry=MultiPolygon.model_validate_json(row["geojson"]),
        )
