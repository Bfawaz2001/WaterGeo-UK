"""Run manually in Fabric with an existing default Lakehouse attached."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID


def read_thames_discharge(spark: Any, snapshot: str) -> Any:
    """Verify a mounted snapshot before reading its Delta-friendly GeoParquet rows."""
    snapshot = str(UUID(snapshot))
    relative = f"Files/watergeo/thames-discharge-status/{snapshot}"
    mounted = Path("/lakehouse/default") / relative
    manifest = json.loads((mounted / "manifest.json").read_text())
    if manifest["entity"] != "thames-discharge-status":
        raise ValueError("Unexpected WaterGeo entity")
    if manifest["dataset"]["snapshot_id"] != snapshot:
        raise ValueError("Snapshot does not match directory")
    name = "thames-discharge-status.parquet"
    expected = manifest["files"][name]["sha256"]
    with (mounted / name).open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("Export hash mismatch")
    return spark.read.parquet(f"{relative}/{name}")


def save_snapshot_table(frame: Any, snapshot: str) -> None:
    """Consumer-owned opt-in that cannot overwrite an existing table."""
    table = "watergeo_thames_discharge_" + UUID(snapshot).hex
    frame.write.format("delta").mode("errorifexists").saveAsTable(table)
