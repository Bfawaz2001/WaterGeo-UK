"""Print a reproducible synthetic repair report using the read-only database role.

Run from the repository root. This developer experiment does not read publisher
files, access application tables, or approve a repair for ingestion.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from watergeo.core.config import Settings
from watergeo.db.engine import create_database_engine

EXPERIMENT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "geometry_repairs.sql"


def build_report() -> dict[str, Any]:
    query = EXPERIMENT.read_bytes()
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            versions = (
                connection.execute(
                    text("""
                    SELECT version() AS postgres, public.PostGIS_Full_Version() AS postgis,
                           public.PostGIS_GEOS_Version() AS geos
                """)
                )
                .mappings()
                .one()
            )
            rows = connection.execute(text(query.decode("utf-8"))).mappings().all()
        results = []
        for row in rows:
            result = dict(row)
            for prefix in ("original", "candidate"):
                ewkb = bytes.fromhex(result.pop(f"{prefix}_ewkb_hex"))
                result[f"{prefix}_ewkb_sha256"] = hashlib.sha256(ewkb).hexdigest()
            results.append(result)
        return {
            "experiment_version": "synthetic-repairs-v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "experiment_sql_sha256": hashlib.sha256(query).hexdigest(),
            "fixture_source": "tests/fixtures/geometry_repairs.sql",
            "fixture_licence": "MIT (repository-authored synthetic shapes)",
            "coordinate_system": "EPSG:27700; invented planar metre coordinates",
            "geometry_hash_encoding": "Little-endian EWKB (NDR), without normalisation",
            "versions": dict(versions),
            "results": results,
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        report = build_report()
    except Exception as error:
        # Driver traceback frames and connection strings can contain credentials.
        raise SystemExit(f"Repair assessment failed: {type(error).__name__}") from None
    print(json.dumps(report, indent=2, ensure_ascii=False))
