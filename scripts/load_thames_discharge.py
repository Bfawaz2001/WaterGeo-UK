"""Validate and atomically load a Thames Water discharge-status evidence bundle."""

import argparse
from pathlib import Path

from watergeo.core.config import IngestionSettings
from watergeo.db.engine import create_database_engine
from watergeo.db.thames_discharge_ingestion import load_snapshot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    engine = create_database_engine(IngestionSettings())
    try:
        print(load_snapshot(engine, args.evidence_dir))
    finally:
        engine.dispose()
