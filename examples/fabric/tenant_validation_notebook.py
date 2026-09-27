"""Manual Fabric notebook cells for verified files in an attached default Lakehouse."""

from typing import Any, Literal

from lakehouse_consumer import read_watergeo
from lakehouse_consumer import save_snapshot_table as save_supply
from thames_discharge_consumer import (
    read_thames_discharge,
)
from thames_discharge_consumer import (
    save_snapshot_table as save_thames,
)


def validate_and_materialize(
    spark: Any,
    *,
    entity: Literal["water-supply", "thames-discharge-status"],
    snapshot_id: str,
) -> dict[str, Any]:
    """Verify manifest/hash, read Parquet and create one consumer-owned Delta table."""
    if entity == "water-supply":
        frame = read_watergeo(spark, snapshot_id)
        save_supply(frame, snapshot_id)
    else:
        frame = read_thames_discharge(spark, snapshot_id)
        save_thames(frame, snapshot_id)
    return {
        "entity": entity,
        "snapshot_id": snapshot_id,
        "row_count": frame.count(),
        "columns": frame.columns,
    }
