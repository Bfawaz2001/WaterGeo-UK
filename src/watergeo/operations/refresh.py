"""One bounded refresh job. No background scheduler or arbitrary fetch targets."""

import argparse
import logging
import multiprocessing
import re
import signal
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Never, cast
from uuid import uuid4

from sqlalchemy import Connection, Engine, text

from watergeo.api.source_models import SourceName
from watergeo.core.config import IngestionSettings
from watergeo.core.logging import configure_logging
from watergeo.db import catchment_ingestion, hydrology_history_ingestion, hydrology_ingestion
from watergeo.db.engine import create_database_engine
from watergeo.ingestion import catchment_client, hydrology_client, hydrology_history_client
from watergeo.ingestion.hydrology import ID_PATTERN
from watergeo.ingestion.ofwat_boundaries import fetch_boundary_source
from watergeo.ingestion.ofwat_canonical import decode_reviewed_water_supply, load_canonical_snapshot

logger = logging.getLogger(__name__)
LOCK_NAMESPACE = 1464296784  # Distinct from loaders' publication transaction locks.
SOURCE_KEYS = {"ofwat": 1, "hydrology": 2, "hydrology-history": 3, "catchments": 4}


class RefreshCancelled(BaseException):
    """Cancellation must escape source clients' ordinary exception handlers."""


class RefreshBusy(Exception):
    """A cooperating refresh job already owns this source lock."""


@dataclass(frozen=True)
class RefreshRequest:
    source: SourceName
    evidence_dir: Path | None = None
    measure_id: str | None = None
    requested_from: datetime | None = None
    requested_to: datetime | None = None


def event(name: str, request: RefreshRequest, run_id: str, **fields: Any) -> None:
    logger.info(name, extra={"source": request.source, "run_id": run_id, **fields})


@contextmanager
def source_lock(engine: Engine, source: SourceName) -> Iterator[Connection]:
    # The worker owns the lock, so supervisor death cannot release it while that
    # worker continues. A crashed worker's DB socket closes and releases the lock.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        try:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :source)"),
                {"namespace": LOCK_NAMESPACE, "source": SOURCE_KEYS[source]},
            ).scalar_one()
            if not acquired:
                raise RefreshBusy()
            yield connection
        finally:
            # Never return a session-level lock to a connection pool, even on failure.
            connection.invalidate()


def assert_lock(connection: Connection, source: SourceName) -> None:
    held = connection.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory'
            AND pid=pg_backend_pid() AND classid=:namespace AND objid=:source
            AND objsubid=2 AND granted)
    """),
        {"namespace": LOCK_NAMESPACE, "source": SOURCE_KEYS[source]},
    ).scalar_one()
    if not held:
        raise RuntimeError("Refresh lock lost")


def refresh(engine: Engine, request: RefreshRequest, run_id: str) -> dict[str, str]:
    """Existing loaders validate again and atomically publish; evidence is retained."""
    with source_lock(engine, request.source) as lock:
        directory = request.evidence_dir
        if directory is None:
            event("refresh_phase", request, run_id, phase="fetch")
            root = Path("data/raw/refresh") / request.source / run_id
            if request.source == "ofwat":
                fetch_boundary_source(raw_root=root)
                directory = root
            elif request.source == "hydrology":
                directory = hydrology_client.fetch_snapshot(root)
            elif request.source == "catchments":
                directory = catchment_client.fetch_snapshot(root)
            else:
                if not request.measure_id or not request.requested_from or not request.requested_to:
                    raise ValueError("History refresh requires an explicit measure and window")
                directory = hydrology_history_client.fetch_history(
                    request.measure_id, request.requested_from, request.requested_to, root
                )
        event("refresh_phase", request, run_id, phase="validate")
        canonical = None
        if request.source == "ofwat":
            canonical = decode_reviewed_water_supply(raw_root=directory)
        elif request.source == "hydrology":
            hydrology_client.read_snapshot(directory)
        elif request.source == "catchments":
            catchment_client.read_snapshot(directory)
        else:
            hydrology_history_client.read_history(directory)
        # Long network retrieval must not continue to publication after losing its lock.
        assert_lock(lock, request.source)
        event("refresh_phase", request, run_id, phase="load")
        if request.source == "ofwat":
            if canonical is None:
                raise ValueError("Missing canonical boundary data")
            result = load_canonical_snapshot(engine, canonical)
            return {"status": result.status, "snapshot_id": str(result.snapshot_id)}
        if request.source == "hydrology":
            loaded = hydrology_ingestion.load_snapshot(engine, directory)
        elif request.source == "catchments":
            loaded = catchment_ingestion.load_snapshot(engine, directory)
        else:
            loaded = hydrology_history_ingestion.load_history(engine, directory)
        return {
            "status": str(loaded["status"]),
            "snapshot_id": str(loaded.get("snapshot_id", loaded.get("retrieval_id"))),
        }


def _cancel(signum: int, frame: Any) -> None:
    raise RefreshCancelled()


def _worker(request: RefreshRequest, run_id: str) -> None:
    configure_logging("INFO")
    signal.signal(signal.SIGTERM, _cancel)
    signal.signal(signal.SIGINT, _cancel)
    engine = None
    exit_code = 1
    try:
        engine = create_database_engine(IngestionSettings(), statement_timeout_ms=60000)
        result = refresh(engine, request, run_id)
        event("refresh_complete", request, run_id, phase="published", **result)
        exit_code = 0
    except RefreshBusy:
        event("refresh_busy", request, run_id)
        exit_code = 3
    except RefreshCancelled:
        event("refresh_interrupted", request, run_id)
        exit_code = 5
    except Exception as error:
        event("refresh_failed", request, run_id, error_type=type(error).__name__)
    finally:
        if engine is not None:
            engine.dispose()
    raise SystemExit(exit_code)


def supervise(
    process: BaseProcess,
    request: RefreshRequest,
    run_id: str,
    timeout_seconds: int,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    started = clock()
    next_progress = started + 30
    try:
        process.start()
        while process.is_alive():
            now = clock()
            if now - started >= timeout_seconds:
                event("refresh_timeout", request, run_id)
                return 4
            if now >= next_progress:
                event("refresh_progress", request, run_id, elapsed_seconds=int(now - started))
                next_progress = now + 30
            process.join(timeout=min(1, timeout_seconds - (now - started)))
        return process.exitcode if process.exitcode in (0, 1, 3, 5) else 1
    except (KeyboardInterrupt, RefreshCancelled):
        event("refresh_interrupted", request, run_id)
        return 5
    except Exception as error:
        event("refresh_failed", request, run_id, error_type=type(error).__name__)
        return 1
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            process.close()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse's default error includes arbitrary supplied arguments.
        logger.error("refresh_invalid_arguments")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    configure_logging("INFO")
    parser = SafeParser(description=__doc__)
    parser.add_argument("source", choices=tuple(SOURCE_KEYS))
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--measure-id")
    parser.add_argument("--from", dest="requested_from")
    parser.add_argument("--to", dest="requested_to")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    start = end = None
    try:
        if not 30 <= args.timeout_seconds <= 86400:
            raise ValueError()
        history_args = (args.measure_id, args.requested_from, args.requested_to)
        if args.source == "hydrology-history" and args.evidence_dir is None:
            if not all(history_args) or not re.fullmatch(ID_PATTERN, args.measure_id):
                raise ValueError()
            start, end = hydrology_history_client.validate_window(
                datetime.fromisoformat(args.requested_from),
                datetime.fromisoformat(args.requested_to),
            )
        elif any(history_args):
            raise ValueError()
        if args.evidence_dir is not None and not args.evidence_dir.is_dir():
            raise ValueError()
    except (ValueError, TypeError, OSError):
        parser.error("Invalid request")
    request = RefreshRequest(
        cast(SourceName, args.source), args.evidence_dir, args.measure_id, start, end
    )
    run_id = str(uuid4())
    event("refresh_started", request, run_id)
    process = multiprocessing.get_context("spawn").Process(target=_worker, args=(request, run_id))
    previous = signal.signal(signal.SIGTERM, _cancel)
    try:
        return supervise(process, request, run_id, args.timeout_seconds)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
