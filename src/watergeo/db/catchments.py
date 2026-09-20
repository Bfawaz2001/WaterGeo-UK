"""Snapshot-pinned read-only Catchment Data Explorer queries."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from watergeo.api.catchment_models import (
    Dataset,
    ManagementCatchmentDetail,
    ManagementCatchmentPage,
    OperationalCatchmentDetail,
    OperationalCatchmentPage,
    RiverBasinDistrictDetail,
    RiverBasinDistrictPage,
    WaterBodyDetail,
    WaterBodyGeometryCollection,
    WaterBodyPage,
)
from watergeo.ingestion.catchments import PLAN_VERSION, ROOT, VERSION

ATTRIBUTION = "© Environment Agency copyright and/or database right 2026. All rights reserved."
MAX_GEOMETRY_OUTPUT_BYTES = 8 * 1024 * 1024


class CatchmentUnavailable(Exception):
    """No compatible catchment snapshot or stored contract failure."""


class CatchmentEntityNotFound(Exception):
    """Requested catchment entity does not exist in the selected snapshot."""


class CatchmentGeometryTooLarge(Exception):
    """Serialized geometry exceeds the public output limit."""


class CatchmentQueries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def dataset(self, snapshot_id: UUID | None = None) -> Dataset:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT *
                        FROM watergeo.catchment_snapshot
                        WHERE normalization_version = :version
                          AND plan_version = :plan_version
                          AND (CAST(:id AS uuid) IS NULL OR id = :id)
                        ORDER BY retrieval_completed_at DESC, id DESC
                        LIMIT 1
                    """),
                    {
                        "version": VERSION,
                        "plan_version": PLAN_VERSION,
                        "id": snapshot_id,
                    },
                )
                .mappings()
                .first()
            )

        if row is None:
            raise CatchmentUnavailable()

        return Dataset.model_validate(
            {
                **row,
                "snapshot_id": row["id"],
                "source_url": ROOT,
                "request_manifest": row["manifest"],
                "attribution": ATTRIBUTION,
            }
        )

    @staticmethod
    def _next_after(rows: list[Any], limit: int, id_column: str) -> str | None:
        if len(rows) <= limit:
            return None
        return str(rows[limit - 1][id_column])

    def river_basin_districts(
        self, dataset: Dataset, *, limit: int, after_id: str | None
    ) -> RiverBasinDistrictPage:
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    text("""
                        SELECT river_basin_district_id, name, publisher_uri
                        FROM watergeo.catchment_river_basin_district
                        WHERE snapshot_id = :snapshot_id
                          AND (
                              CAST(:after_id AS text) IS NULL
                              OR river_basin_district_id COLLATE "C" > :after_id
                          )
                        ORDER BY river_basin_district_id COLLATE "C"
                        LIMIT :limit
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "after_id": after_id,
                        "limit": limit + 1,
                    },
                ).mappings()
            )

        return RiverBasinDistrictPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": self._next_after(rows, limit, "river_basin_district_id"),
            }
        )

    def river_basin_district(self, dataset: Dataset, entity_id: str) -> RiverBasinDistrictDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT snapshot_id, river_basin_district_id, name,
                               publisher_uri, source_fields
                        FROM watergeo.catchment_river_basin_district
                        WHERE snapshot_id = :snapshot_id
                          AND river_basin_district_id = :entity_id
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "entity_id": entity_id,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CatchmentEntityNotFound()
        return RiverBasinDistrictDetail.model_validate(row)

    def management_catchments(
        self, dataset: Dataset, *, limit: int, after_id: str | None
    ) -> ManagementCatchmentPage:
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    text("""
                        SELECT management_catchment_id, river_basin_district_id,
                               name, publisher_uri
                        FROM watergeo.catchment_management
                        WHERE snapshot_id = :snapshot_id
                          AND (
                              CAST(:after_id AS text) IS NULL
                              OR management_catchment_id COLLATE "C" > :after_id
                          )
                        ORDER BY management_catchment_id COLLATE "C"
                        LIMIT :limit
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "after_id": after_id,
                        "limit": limit + 1,
                    },
                ).mappings()
            )

        return ManagementCatchmentPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": self._next_after(rows, limit, "management_catchment_id"),
            }
        )

    def management_catchment(self, dataset: Dataset, entity_id: str) -> ManagementCatchmentDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT snapshot_id, management_catchment_id,
                               river_basin_district_id, name, publisher_uri,
                               source_fields
                        FROM watergeo.catchment_management
                        WHERE snapshot_id = :snapshot_id
                          AND management_catchment_id = :entity_id
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "entity_id": entity_id,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CatchmentEntityNotFound()
        return ManagementCatchmentDetail.model_validate(row)

    def operational_catchments(
        self, dataset: Dataset, *, limit: int, after_id: str | None
    ) -> OperationalCatchmentPage:
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    text("""
                        SELECT operational_catchment_id, management_catchment_id,
                               river_basin_district_id, name, publisher_uri
                        FROM watergeo.catchment_operational
                        WHERE snapshot_id = :snapshot_id
                          AND (
                              CAST(:after_id AS text) IS NULL
                              OR operational_catchment_id COLLATE "C" > :after_id
                          )
                        ORDER BY operational_catchment_id COLLATE "C"
                        LIMIT :limit
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "after_id": after_id,
                        "limit": limit + 1,
                    },
                ).mappings()
            )

        return OperationalCatchmentPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": self._next_after(rows, limit, "operational_catchment_id"),
            }
        )

    def operational_catchment(self, dataset: Dataset, entity_id: str) -> OperationalCatchmentDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT snapshot_id, operational_catchment_id,
                               management_catchment_id, river_basin_district_id,
                               name, publisher_uri, source_fields
                        FROM watergeo.catchment_operational
                        WHERE snapshot_id = :snapshot_id
                          AND operational_catchment_id = :entity_id
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "entity_id": entity_id,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CatchmentEntityNotFound()
        return OperationalCatchmentDetail.model_validate(row)

    def water_bodies(self, dataset: Dataset, *, limit: int, after_id: str | None) -> WaterBodyPage:
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    text("""
                        SELECT water_body_id, operational_catchment_id,
                               management_catchment_id, river_basin_district_id,
                               name, water_body_type, publisher_uri
                        FROM watergeo.catchment_water_body
                        WHERE snapshot_id = :snapshot_id
                          AND (
                              CAST(:after_id AS text) IS NULL
                              OR water_body_id COLLATE "C" > :after_id
                          )
                        ORDER BY water_body_id COLLATE "C"
                        LIMIT :limit
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "after_id": after_id,
                        "limit": limit + 1,
                    },
                ).mappings()
            )

        return WaterBodyPage.model_validate(
            {
                "dataset": dataset,
                "items": rows[:limit],
                "next_after_id": self._next_after(rows, limit, "water_body_id"),
            }
        )

    def water_body(self, dataset: Dataset, entity_id: str) -> WaterBodyDetail:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                        SELECT snapshot_id, water_body_id,
                               operational_catchment_id, management_catchment_id,
                               river_basin_district_id, name, water_body_type,
                               publisher_uri, source_fields
                        FROM watergeo.catchment_water_body
                        WHERE snapshot_id = :snapshot_id
                          AND water_body_id = :entity_id
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "entity_id": entity_id,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CatchmentEntityNotFound()

        return WaterBodyDetail.model_validate(
            {
                **row,
                "geometry_url": f"/v1/catchments/water-bodies/{entity_id}/geometry",
            }
        )

    def water_body_geometry(self, dataset: Dataset, entity_id: str) -> WaterBodyGeometryCollection:
        with self.engine.connect() as connection:
            exists = connection.execute(
                text("""
                    SELECT 1
                    FROM watergeo.catchment_water_body
                    WHERE snapshot_id = :snapshot_id
                      AND water_body_id = :entity_id
                """),
                {
                    "snapshot_id": dataset.snapshot_id,
                    "entity_id": entity_id,
                },
            ).first()

            if exists is None:
                raise CatchmentEntityNotFound()

            rows = list(
                connection.execute(
                    text("""
                        SELECT feature_index, geometry_type_uri, geometry_kind,
                               public.ST_AsGeoJSON(geom, 15, 0)::jsonb AS geometry,
                               source_fields
                        FROM watergeo.catchment_water_body_geometry
                        WHERE snapshot_id = :snapshot_id
                          AND water_body_id = :entity_id
                        ORDER BY feature_index
                    """),
                    {
                        "snapshot_id": dataset.snapshot_id,
                        "entity_id": entity_id,
                    },
                ).mappings()
            )

        payload = {
            "type": "FeatureCollection",
            "water_body_id": entity_id,
            "snapshot_id": dataset.snapshot_id,
            "features": [
                {
                    "type": "Feature",
                    "id": f"{entity_id}:{row['feature_index']}",
                    "geometry": row["geometry"],
                    "properties": {
                        "feature_index": row["feature_index"],
                        "geometry_kind": row["geometry_kind"],
                        "geometry_type_uri": row["geometry_type_uri"],
                        "source_fields": row["source_fields"],
                    },
                }
                for row in rows
            ],
        }

        result = WaterBodyGeometryCollection.model_validate(payload)

        if len(result.model_dump_json().encode()) > MAX_GEOMETRY_OUTPUT_BYTES:
            raise CatchmentGeometryTooLarge()

        return result
