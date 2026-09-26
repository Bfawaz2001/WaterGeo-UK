"""Atomic insert-only publication for Thames Water discharge status."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from watergeo.ingestion.thames_discharge import (
    API_VERSION,
    VERSION,
    NormalizedDischargeStatus,
    ThamesDischargeError,
)
from watergeo.ingestion.thames_discharge_client import read_snapshot


def verify_stored(
    connection: Connection, identity: UUID, expected: NormalizedDischargeStatus
) -> None:
    metadata = (
        connection.execute(
            text("SELECT * FROM watergeo.thames_discharge_snapshot WHERE id=:id"), {"id": identity}
        )
        .mappings()
        .one()
    )
    sites = [
        {
            **dict(row),
            "status_changed": row["status_changed"].isoformat(),
            "most_recent_discharge_start": row["most_recent_discharge_start"].isoformat()
            if row["most_recent_discharge_start"]
            else None,
            "most_recent_discharge_stop": row["most_recent_discharge_stop"].isoformat()
            if row["most_recent_discharge_stop"]
            else None,
        }
        for row in connection.execute(
            text("""
            SELECT site_id,location_name,permit_number,grid_reference,easting,northing,
                receiving_watercourse,alert_status,status_changed,alert_past_48_hours,
                most_recent_discharge_start,most_recent_discharge_stop,source_fields
            FROM watergeo.thames_discharge_site WHERE snapshot_id=:id
            ORDER BY site_id COLLATE "C"
        """),
            {"id": identity},
        ).mappings()
    ]
    actual = NormalizedDischargeStatus(sites)
    manifest = metadata["manifest"]
    if (
        metadata["api_version"] != API_VERSION
        or metadata["normalization_version"] != VERSION
        or metadata["normalized_sha256"] != expected.sha256
        or actual.sha256 != expected.sha256
        or metadata["site_count"] != len(sites)
        or manifest.get("content_sha256") != metadata["content_sha256"]
        or manifest.get("normalized_sha256") != expected.sha256
    ):
        raise ThamesDischargeError("Stored Thames Water snapshot content mismatch")


def load_snapshot(engine: Engine, directory: Path) -> dict[str, Any]:
    manifest, data = read_snapshot(directory)
    discharging = sum(row["alert_status"] == "Discharging" for row in data.sites)
    offline = sum(row["alert_status"] == "Offline" for row in data.sites)
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(1464296783, 8)"))
        existing = connection.execute(
            text("""
            SELECT id FROM watergeo.thames_discharge_snapshot
            WHERE content_sha256=:hash AND normalization_version=:version
        """),
            {"hash": manifest["content_sha256"], "version": VERSION},
        ).scalar_one_or_none()
        if existing is not None:
            verify_stored(connection, existing, data)
            return {
                "status": "existing",
                "snapshot_id": str(existing),
                "site_count": len(data.sites),
            }
        identity = uuid4()
        connection.execute(
            text("""
            INSERT INTO watergeo.thames_discharge_snapshot
                (id,api_version,retrieval_started_at,retrieval_completed_at,content_sha256,
                 normalized_sha256,normalization_version,site_count,discharging_count,
                 offline_count,manifest)
            VALUES (:id,:api_version,:started,:completed,:content,:normalized,:version,
                :count,:discharging,:offline,CAST(:manifest AS jsonb))
        """),
            {
                "id": identity,
                "api_version": API_VERSION,
                "started": manifest["retrieval_started_at"],
                "completed": manifest["retrieval_completed_at"],
                "content": manifest["content_sha256"],
                "normalized": data.sha256,
                "version": VERSION,
                "count": len(data.sites),
                "discharging": discharging,
                "offline": offline,
                "manifest": json.dumps(manifest, allow_nan=False),
            },
        )
        connection.execute(
            text("""
            INSERT INTO watergeo.thames_discharge_site
                (snapshot_id,site_id,location_name,permit_number,grid_reference,easting,
                 northing,geom,receiving_watercourse,alert_status,status_changed,
                 alert_past_48_hours,most_recent_discharge_start,
                 most_recent_discharge_stop,source_fields)
            VALUES (:snapshot_id,:site_id,:location_name,:permit_number,:grid_reference,
                :easting,:northing,public.ST_Transform(public.ST_SetSRID(
                    public.ST_MakePoint(:easting,:northing),27700),4326),
                :receiving_watercourse,:alert_status,:status_changed,
                :alert_past_48_hours,:most_recent_discharge_start,
                :most_recent_discharge_stop,CAST(:source_fields AS jsonb))
        """),
            [
                {
                    **row,
                    "snapshot_id": identity,
                    "source_fields": json.dumps(row["source_fields"], allow_nan=False),
                }
                for row in data.sites
            ],
        )
        verify_stored(connection, identity, data)
    return {"status": "inserted", "snapshot_id": str(identity), "site_count": len(data.sites)}
