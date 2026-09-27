"""Prepare a complete local WaterGeo demo through existing refresh contracts."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal, cast

from sqlalchemy import Engine

from watergeo.api.source_models import SourceStatus
from watergeo.core.config import Settings
from watergeo.db.engine import create_database_engine, database_is_ready
from watergeo.db.source_status import source_statuses
from watergeo.operations.refresh import main as refresh_main

DemoSource = Literal[
    "ofwat",
    "hydrology",
    "catchments",
    "water-quality",
    "stream-reservoir-levels",
    "thames-discharge-status",
]

SOURCES: tuple[DemoSource, ...] = (
    "ofwat",
    "hydrology",
    "catchments",
    "water-quality",
    "stream-reservoir-levels",
    "thames-discharge-status",
)
LABELS = {
    "ofwat": "Water supply",
    "hydrology": "Hydrology",
    "catchments": "Catchments",
    "water-quality": "Water Quality",
    "stream-reservoir-levels": "Reservoir levels",
    "thames-discharge-status": "Thames discharge",
}
SEMANTICS = {
    "ofwat": "static/versioned",
    "hydrology": "dynamic/latest available",
    "catchments": "static/versioned",
    "water-quality": "dynamic/latest available",
    "stream-reservoir-levels": "static/versioned",
    "thames-discharge-status": "dynamic/latest available",
}
TIMEOUTS = {
    "ofwat": 600,
    "hydrology": 3600,
    "catchments": 7200,
    "water-quality": 3600,
    "stream-reservoir-levels": 900,
    "thames-discharge-status": 900,
}


def retained_candidates(source: DemoSource, root: Path = Path("data")) -> list[Path]:
    """Return newest local bundle first; readers still verify it before publication."""
    raw = root / "raw"
    patterns: dict[DemoSource, tuple[str, ...]] = {
        "ofwat": ("ofwat/water-supply",),
        "hydrology": ("environment-agency/hydrology/*",),
        "catchments": ("environment-agency/catchments/*",),
        "water-quality": ("environment-agency/water-quality/sampling-points/*",),
        "stream-reservoir-levels": ("stream/severn-trent-reservoir-levels/*",),
        "thames-discharge-status": (
            "thames-water/discharge-status/*",
            "refresh/thames-discharge-status/*/*",
        ),
    }
    candidates: list[Path] = []
    for pattern in patterns[source]:
        candidates.extend(raw.glob(pattern))
    # Local archives add evidence-index.json and are immutable archive objects,
    # rather than source-reader bundles. Raw retained bundles have their own
    # source manifests and are validated again by the refresh contract.
    directories = {
        path.resolve()
        for path in candidates
        if path.is_dir() and not (path / "evidence-index.json").exists()
    }
    return sorted(directories, key=lambda path: path.stat().st_mtime, reverse=True)


def status_map(engine: Engine, settings: Settings) -> dict[str, SourceStatus]:
    return {item.source: item for item in source_statuses(engine, settings).sources}


def print_summary(statuses: dict[str, SourceStatus], requested: Sequence[DemoSource]) -> None:
    print("\nWaterGeo local demo\n")
    for source in requested:
        status = statuses[source]
        if status.availability == "available":
            marker = "✓"
            state = "available"
            if status.retrieval_freshness == "stale":
                state = "available (stale)"
        else:
            marker = "○"
            state = "not loaded"
        print(f"{marker} {LABELS[source]:<22} {state:<18} {SEMANTICS[source]}")


def run(
    requested: Sequence[DemoSource],
    *,
    status_only: bool,
    dry_run: bool,
    offline: bool,
    engine: Engine,
    settings: Settings,
    refresher: Callable[[list[str]], int] = refresh_main,
    data_root: Path = Path("data"),
) -> int:
    if not database_is_ready(engine):
        print("✗ Database is not ready at migration head.")
        return 2
    before = status_map(engine, settings)
    missing = [source for source in requested if before[source].availability != "available"]
    print_summary(before, requested)
    if status_only or not missing:
        return 0 if not missing else 1
    if dry_run:
        for source in missing:
            candidates = retained_candidates(source, data_root)
            action = f"replay {candidates[0]}" if candidates else "retrieve from fixed publisher"
            print(f"DRY RUN {LABELS[source]}: {action}")
        return 1

    failures: set[DemoSource] = set()
    for source in missing:
        candidates = retained_candidates(source, data_root)
        args = [source, "--timeout-seconds", str(TIMEOUTS[source])]
        if candidates:
            args.extend(("--evidence-dir", str(candidates[0])))
            print(f"\n→ {LABELS[source]}: replaying retained evidence {candidates[0]}")
        elif offline:
            print(f"\n✗ {LABELS[source]}: no retained evidence (offline mode)")
            failures.add(source)
            continue
        else:
            print(f"\n→ {LABELS[source]}: no retained evidence; retrieving from fixed publisher")
        if refresher(args) != 0:
            print(f"✗ {LABELS[source]}: refresh failed")
            failures.add(source)
        else:
            print(f"✓ {LABELS[source]}: refresh completed")

    after = status_map(engine, settings)
    print_summary(after, requested)
    unavailable = {source for source in requested if after[source].availability != "available"}
    return 1 if failures or unavailable else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--status", action="store_true", help="inspect availability only")
    result.add_argument("--dry-run", action="store_true", help="show missing-source actions")
    result.add_argument(
        "--offline",
        action="store_true",
        help="use retained evidence only; never contact publishers",
    )
    result.add_argument(
        "--source", action="append", choices=SOURCES, help="request one source (repeatable)"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    requested = tuple(dict.fromkeys(args.source or SOURCES))
    settings = Settings()
    engine = create_database_engine(settings, statement_timeout_ms=60_000)
    try:
        return run(
            cast(Sequence[DemoSource], requested),
            status_only=args.status,
            dry_run=args.dry_run,
            offline=args.offline,
            engine=engine,
            settings=settings,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
