"""Sequentially refresh the six dynamic sources used by the local demo."""

import argparse
from collections.abc import Callable

from watergeo.api.source_models import SourceName
from watergeo.operations.refresh import main as refresh_main

DYNAMIC_SOURCES: tuple[SourceName, ...] = (
    "hydrology",
    "water-quality",
    "thames-discharge-status",
    "rainfall",
    "flood-monitoring",
    "bathing-waters",
)
OUTCOMES = {
    0: "accepted",
    1: "failed",
    3: "busy",
    4: "timed out",
    5: "interrupted",
}


def run(
    *,
    refresher: Callable[[list[str]], int] = refresh_main,
    output: Callable[[str], None] = print,
) -> int:
    """Run the existing governed refresh command once per dynamic source."""
    results: list[int] = []
    for source in DYNAMIC_SOURCES:
        output(f"Refreshing {source}...")
        code = refresher([source])
        results.append(code)
        output(f"{source}: {OUTCOMES.get(code, f'failed (exit {code})')}")
        if code == 5:
            break

    accepted = results.count(0)
    failed = len(results) - accepted
    not_run = len(DYNAMIC_SOURCES) - len(results)
    output(f"Dynamic refresh summary: {accepted} accepted, {failed} failed, {not_run} not run.")
    output(
        "Successful results are latest accepted WaterGeo retrievals, not publisher-live guarantees."
    )
    return 1 if failed or not_run else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
