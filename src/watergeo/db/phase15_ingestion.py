"""Atomic publication of validated Phase 15 national products."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from watergeo.evidence import EvidenceIdentity
from watergeo.ingestion.phase15_client import read_bundle
from watergeo.ingestion.phase15_sources import VERSION, NormalizedProduct, Phase15SourceError


def _insert_entities(connection: Any, identity: UUID, product: NormalizedProduct) -> None:
    if product.source == "rainfall":
        connection.execute(
            text("""
                INSERT INTO watergeo.rainfall_station
                    (snapshot_id,station_id,publisher_uri,display_name,geom,grid_reference,
                     latest_observed_at,latest_value_mm,latest_value,latest_unit,
                     latest_period_seconds,source_fields)
                VALUES (:snapshot_id,:station_id,:publisher_uri,:display_name,
                    CASE WHEN :longitude IS NULL THEN NULL ELSE
                        public.ST_SetSRID(public.ST_MakePoint(:longitude,:latitude),4326) END,
                    :grid_reference,:latest_observed_at,:latest_value_mm,:latest_value,
                    :latest_unit,:latest_period_seconds,
                    CAST(:source_fields AS jsonb))
            """),
            [
                {**row, "snapshot_id": identity, "source_fields": json.dumps(row["source_fields"])}
                for row in product.entities
            ],
        )
    elif product.source == "flood-monitoring":
        if product.entities:
            connection.execute(
                text("""
                INSERT INTO watergeo.flood_area
                    (snapshot_id,area_id,publisher_uri,label,description,county,river_or_sea,
                     centroid,geom,geometry_policy,source_fields)
                VALUES (:snapshot_id,:area_id,:publisher_uri,:label,:description,:county,
                    :river_or_sea,public.ST_SetSRID(public.ST_MakePoint(:longitude,:latitude),4326),
                    public.ST_SetSRID(public.ST_GeomFromGeoJSON(:geometry),4326),
                    CAST(:geometry_policy AS jsonb),
                    CAST(:source_fields AS jsonb))
            """),
                [
                    {
                        **row,
                        "snapshot_id": identity,
                        "geometry": json.dumps(row["geometry"]),
                        "geometry_policy": json.dumps(row["geometry_policy"]),
                        "source_fields": json.dumps(row["source_fields"]),
                    }
                    for row in product.entities
                ],
            )
        if product.secondary:
            connection.execute(
                text("""
                INSERT INTO watergeo.flood_warning
                    (snapshot_id,warning_id,area_id,description,severity,severity_level,
                     message,is_tidal,time_raised,time_message_changed,time_severity_changed,
                     source_fields)
                VALUES (:snapshot_id,:warning_id,:area_id,:description,:severity,:severity_level,
                    :message,:is_tidal,:time_raised,:time_message_changed,:time_severity_changed,
                    CAST(:source_fields AS jsonb))
            """),
                [
                    {
                        **row,
                        "snapshot_id": identity,
                        "source_fields": json.dumps(row["source_fields"]),
                    }
                    for row in product.secondary
                ],
            )
    elif product.source == "bathing-waters":
        connection.execute(
            text("""
                INSERT INTO watergeo.bathing_water
                    (snapshot_id,bathing_water_id,publisher_uri,name,geom,classification,
                     assessment_year,latest_sample_uri,latest_risk_prediction,source_fields)
                VALUES (:snapshot_id,:bathing_water_id,:publisher_uri,:name,
                    public.ST_SetSRID(public.ST_MakePoint(:longitude,:latitude),4326),
                    :classification,:assessment_year,:latest_sample_uri,
                    CAST(:latest_risk_prediction AS jsonb),CAST(:source_fields AS jsonb))
            """),
            [
                {
                    **row,
                    "snapshot_id": identity,
                    "latest_risk_prediction": json.dumps(row["latest_risk_prediction"]),
                    "source_fields": json.dumps(row["source_fields"]),
                }
                for row in product.entities
            ],
        )
    else:
        connection.execute(
            text("""
                INSERT INTO watergeo.company_performance_company
                    (snapshot_id,company_id,company_name,boundary_company_acronym)
                VALUES (:snapshot_id,:company_id,:company_name,:boundary_company_acronym)
            """),
            [{**row, "snapshot_id": identity} for row in product.entities],
        )
        connection.execute(
            text("""
                INSERT INTO watergeo.company_performance_measure
                    (snapshot_id,company_id,reporting_period,measure_code,measure_name,value,
                     value_state,unit,definition,publication,source_fields)
                VALUES (:snapshot_id,:company_id,:reporting_period,:measure_code,:measure_name,
                    :value,:value_state,:unit,:definition,:publication,
                    CAST(:source_fields AS jsonb))
            """),
            [
                {**row, "snapshot_id": identity, "source_fields": json.dumps(row["source_fields"])}
                for row in product.secondary
            ],
        )


def load_snapshot(
    engine: Engine,
    directory: Path,
    normalize: Any,
    *,
    evidence: EvidenceIdentity | None = None,
) -> dict[str, Any]:
    manifest, product = read_bundle(directory, normalize)
    if evidence is not None:
        manifest = {**manifest, "durable_evidence": evidence.as_manifest()}
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 15)"))
        existing = connection.execute(
            text("""
                SELECT id FROM watergeo.national_source_snapshot
                WHERE source_key=:source AND content_sha256=:hash
                    AND normalization_version=:version
            """),
            {"source": product.source, "hash": manifest["content_sha256"], "version": VERSION},
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "status": "existing",
                "snapshot_id": str(existing),
                "entity_count": len(product.entities),
                "secondary_count": len(product.secondary),
                "skipped_count": product.skipped_count,
            }
        identity = uuid4()
        connection.execute(
            text("""
                INSERT INTO watergeo.national_source_snapshot
                    (id,source_key,retrieval_started_at,retrieval_completed_at,content_sha256,
                     normalized_sha256,normalization_version,entity_count,secondary_count,
                     skipped_count,manifest)
                VALUES (:id,:source,:started,:completed,:content,:normalized,:version,
                    :entities,:secondary,:skipped,CAST(:manifest AS jsonb))
            """),
            {
                "id": identity,
                "source": product.source,
                "started": manifest["retrieval_started_at"],
                "completed": manifest["retrieval_completed_at"],
                "content": manifest["content_sha256"],
                "normalized": product.sha256,
                "version": VERSION,
                "entities": len(product.entities),
                "secondary": len(product.secondary),
                "skipped": product.skipped_count,
                "manifest": json.dumps(manifest),
            },
        )
        _insert_entities(connection, identity, product)
        stored = connection.execute(
            text(
                "SELECT entity_count,secondary_count,skipped_count "
                "FROM watergeo.national_source_snapshot WHERE id=:id"
            ),
            {"id": identity},
        ).one()
        if stored != (len(product.entities), len(product.secondary), product.skipped_count):
            raise Phase15SourceError("Stored Phase 15 snapshot count mismatch")
    return {
        "status": "inserted",
        "snapshot_id": str(identity),
        "entity_count": len(product.entities),
        "secondary_count": len(product.secondary),
        "skipped_count": product.skipped_count,
    }
