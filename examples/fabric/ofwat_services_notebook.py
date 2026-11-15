"""Manual Fabric notebook cells; local validation also works without Spark.

Install the reviewed WaterGeo wheel with its exports extra in the consumer's
notebook environment. Attach a consumer-owned Lakehouse. Upload the complete
immutable bundle under Files/watergeo/ofwat-services/<edition>/, then copy these
cells. Nothing runs on import; no tenant credentials or SDK are used.
"""

from pathlib import Path
from typing import Any

from watergeo.service_boundaries import validate_service_bundle

TABLES = (
    "water-supply",
    "sewerage",
    "companies",
    "services",
    "areas",
    "company-area-bridge",
)


def read_services(spark: Any, edition: str, expected_manifest_sha256: str) -> dict[str, Any]:
    """Validate all files, geometry, relationships and provenance before Spark reads."""
    if not edition or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in edition):
        raise ValueError("Use a simple edition directory name")
    relative = f"Files/watergeo/ofwat-services/{edition}"
    mounted = Path("/lakehouse/default") / relative
    manifest = validate_service_bundle(mounted, expected_manifest_sha256)
    frames = {name: spark.read.parquet(f"{relative}/{name}.parquet") for name in TABLES}
    # Spark/Delta do not promise to retain GeoParquet file-level key/value metadata.
    # Keep the uploaded GeoParquet + manifest as immutable Files artifacts; binary
    # WKB remains binary in the optional Delta tables, without text conversion.
    return {
        "manifest": manifest,
        "frames": frames,
        "source_crs": "EPSG:27700",
        "manifest_sha256": expected_manifest_sha256,
    }


def save_delta_tables(bundle: dict[str, Any], prefix: str) -> None:
    """Consumer opt-in only. Existing tables fail rather than being overwritten.

    Each table commits independently: a failure may leave preceding tables. Use a
    new prefix when retrying; no claim of a cross-table Delta transaction is made.
    """
    if not prefix or not prefix[0].isalpha() or not all(c.isalnum() or c == "_" for c in prefix):
        raise ValueError("Prefix must be an SQL-safe table prefix")
    from pyspark.sql import functions as f  # type: ignore[import-not-found]

    for name, frame in bundle["frames"].items():
        enriched = frame.withColumn(
            "bundle_manifest_sha256", f.lit(bundle["manifest_sha256"])
        ).withColumn("source_geometry_crs", f.lit(bundle["source_crs"]))
        enriched.write.format("delta").mode("errorifexists").saveAsTable(
            f"{prefix}_{name.replace('-', '_')}"
        )


# Cell 1: supply the externally recorded hash, not one read from the uploaded bundle.
# bundle = read_services(spark, "april-2024-v1", "<reviewed manifest SHA-256>")
# Cell 2: inspect original geometry and quarantine flags.
# display(bundle["frames"]["sewerage"].select(
#     "boundary_id", "COMPANY", "AreaServed", "source_valid", "coverage_eligible", "geometry"))
# Cell 3: exclude invalid publisher geometry from any coverage/spatial calculation.
# eligible = bundle["frames"]["sewerage"].filter("coverage_eligible = true")
# Cell 4 (OPTIONAL, creates tables in the attached consumer-owned Lakehouse):
# save_delta_tables(bundle, "ofwat_april2024_v1")
