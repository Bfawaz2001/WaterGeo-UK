"""Write read-only WGS84 presentation evidence for the loaded reviewed snapshot."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from watergeo.core.config import Settings
from watergeo.db.engine import create_database_engine
from watergeo.db.presentation_assessment import PresentationAssessmentError, assess_presentation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New JSON report path; never overwritten")
    args = parser.parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = args.output or Path(
        f"data/validation/ofwat/water-supply/presentation-assessment-{timestamp}.json"
    )
    if path.exists():
        print("Report already exists; choose a new --output path.")
        return 1
    engine = None
    try:
        engine = create_database_engine(Settings(), statement_timeout_ms=60_000)
        report = assess_presentation(engine)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive file creation prevents overwriting a previous review artifact.
        with path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except (ValidationError, SQLAlchemyError, PresentationAssessmentError, OSError) as error:
        # Configuration and driver messages can contain credentials or private SQL.
        print(f"Presentation assessment failed ({type(error).__name__}).")
        print("Check database readiness, reviewed data and whether the report already exists.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(f"Assessed {len(report['baseline'])} areas; failures: {report['failed_source_ids']}")
    print("This diagnostic does not approve transformations or change the API.")
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
