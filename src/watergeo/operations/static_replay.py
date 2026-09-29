"""Replay one reviewed, local evidence plan into an ephemeral static-build database."""

import argparse
import json
from pathlib import Path

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine
from watergeo.operations.refresh import RefreshRequest, refresh

REQUIRED = {
    "ofwat",
    "hydrology",
    "catchments",
    "water-quality",
    "stream-reservoir-levels",
    "thames-discharge-status",
    "rainfall",
    "flood-monitoring",
    "bathing-waters",
    "company-performance",
}


def replay(plan_path: Path) -> None:
    root = plan_path.resolve().parent
    value = json.loads(plan_path.read_bytes())
    if not isinstance(value, dict) or value.get("version") != "watergeo-static-replay-v1":
        raise ValueError("Invalid static evidence replay plan")
    sources = value.get("sources")
    if not isinstance(sources, list) or not all(isinstance(row, dict) for row in sources):
        raise ValueError("Invalid static evidence source list")
    names = [row.get("source") for row in sources]
    if len(names) != len(set(names)) or set(names) != REQUIRED:
        raise ValueError("Static evidence plan must contain every required source exactly once")
    engine = create_database_engine(IngestionSettings())
    try:
        for row in sources:
            relative = row.get("evidence_directory")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                raise ValueError("Invalid static evidence directory")
            directory = (root / relative).resolve()
            if root not in directory.parents or not directory.is_dir():
                raise ValueError("Static evidence directory escaped its reviewed bundle")
            result = refresh(
                engine,
                RefreshRequest(row["source"], directory),
                "static-publication-replay",
            )
            if result["status"] not in {"inserted", "existing"}:
                raise ValueError("Static evidence replay did not publish an accepted snapshot")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    arguments = parser.parse_args()
    replay(arguments.plan)


if __name__ == "__main__":
    main()
