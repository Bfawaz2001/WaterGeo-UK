"""Run manually in a Fabric notebook with an existing default Lakehouse attached."""

import hashlib
import json
from pathlib import Path
from typing import Any


def read_watergeo(spark: Any, snapshot: str) -> Any:
    """Verify a mounted bundle before using Spark's existing Parquet reader."""
    from uuid import UUID

    snapshot = str(UUID(snapshot))
    relative = f"Files/watergeo/water-supply/{snapshot}"
    mounted = Path("/lakehouse/default") / relative
    manifest = json.loads((mounted / "manifest.json").read_text())
    if manifest["dataset"]["snapshot_id"] != snapshot:
        raise ValueError("Snapshot does not match directory")
    expected = manifest["files"]["water-supply.parquet"]["sha256"]
    with (mounted / "water-supply.parquet").open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("Export hash mismatch")
    return spark.read.parquet(f"{relative}/water-supply.parquet")


def save_snapshot_table(frame: Any, snapshot: str) -> None:
    """Explicit consumer-side opt-in; never called by WaterGeo or on import."""
    from uuid import UUID

    table = "watergeo_supply_" + UUID(snapshot).hex
    frame.write.format("delta").mode("errorifexists").saveAsTable(table)
