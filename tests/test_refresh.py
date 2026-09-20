import json
import logging
import multiprocessing
import signal
import time
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from watergeo.core.logging import JsonFormatter
from watergeo.operations import refresh as jobs


@pytest.mark.parametrize("body_fails", [False, True])
def test_source_lock_explicit_unlock_then_disposal(body_fails):
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execution_options.return_value = connection
    connection.execute.return_value.scalar_one.return_value = True
    failure = ValueError("body failure")
    try:
        with jobs.source_lock(engine, "hydrology"):
            if body_fails:
                raise failure
    except ValueError as error:
        assert body_fails and error is failure
    calls = connection.execute.call_args_list
    assert len(calls) == 2
    assert str(calls[1].args[0]) == "SELECT pg_advisory_unlock(:namespace, :source)"
    assert calls[1].args[1] == {"namespace": jobs.LOCK_NAMESPACE, "source": 2}
    names = [call[0] for call in connection.mock_calls]
    connection.detach.assert_not_called()
    assert names.index("invalidate") > max(i for i, name in enumerate(names) if name == "execute")
    assert names.index("close") > names.index("invalidate")


@pytest.mark.parametrize("failure_at", ["unlock", "invalidate", "close"])
@pytest.mark.parametrize("body_fails", [False, True])
def test_source_lock_cleanup_failure_preserves_body_error(failure_at, body_fails):
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execution_options.return_value = connection
    connection.execute.return_value.scalar_one.return_value = True
    cleanup_error = RuntimeError("cleanup failure")
    if failure_at == "unlock":
        connection.execute.side_effect = [connection.execute.return_value, cleanup_error]
    else:
        getattr(connection, failure_at).side_effect = cleanup_error
    original = jobs.RefreshCancelled()
    with pytest.raises(BaseException) as caught, jobs.source_lock(engine, "hydrology"):
        if body_fails:
            raise original
    assert caught.value is (original if body_fails else cleanup_error)
    if failure_at == "invalidate":
        connection.detach.assert_called_once()
        names = [call[0] for call in connection.mock_calls]
        assert names.index("invalidate") < names.index("detach") < names.index("close")
    else:
        connection.detach.assert_not_called()
    connection.invalidate.assert_called_once()
    connection.close.assert_called_once()


def test_source_lock_unconfirmed_unlock_fails_closed():
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execution_options.return_value = connection
    connection.execute.return_value.scalar_one.side_effect = [True, False]
    with (
        pytest.raises(RuntimeError, match="release not confirmed"),
        jobs.source_lock(engine, "hydrology"),
    ):
        pass
    connection.invalidate.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        ["unknown-secret"],
        ["hydrology", "--timeout-seconds", "0"],
        ["hydrology", "--measure-id", "private"],
        ["hydrology-history"],
        ["hydrology-history", "--measure-id", "a", "--from", "2026-01-01", "--to", "2026-01-02"],
        [
            "hydrology-history",
            "--measure-id",
            "a",
            "--from",
            "2026-01-01T00:00:00Z",
            "--to",
            "2026-03-01T00:00:00Z",
        ],
        ["hydrology", "--evidence-dir", "/nonexistent-private-evidence"],
    ],
)
def test_invalid_arguments_sanitised(args, capsys):
    with pytest.raises(SystemExit) as error:
        jobs.main(args)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "refresh_invalid_arguments" in output.out
    assert "private" not in output.out + output.err
    assert "unknown-secret" not in output.out + output.err


@pytest.mark.parametrize("code,expected", [(0, 0), (1, 1), (3, 3), (5, 5), (-9, 1)])
def test_worker_exit_codes(code, expected):
    process = MagicMock()
    process.is_alive.return_value = False
    process.exitcode = code
    assert jobs.supervise(process, jobs.RefreshRequest("hydrology"), "run", 30) == expected
    process.close.assert_called_once()


def test_real_spawned_worker_is_stopped_and_reaped_on_deadline():
    process = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(60,))
    start = time.monotonic()
    assert jobs.supervise(process, jobs.RefreshRequest("hydrology"), "run", 0) == 4
    assert time.monotonic() - start < 12
    assert process not in multiprocessing.active_children()


def test_timeout_escalates_to_kill():
    process = MagicMock()
    process.is_alive.side_effect = [True, True, True]
    assert jobs.supervise(process, jobs.RefreshRequest("hydrology"), "run", 0) == 4
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    process.close.assert_called_once()


def test_interrupt_reaps_worker():
    process = MagicMock()
    process.join.side_effect = [KeyboardInterrupt(), None, None]
    process.is_alive.side_effect = [True, True, False]
    assert jobs.supervise(process, jobs.RefreshRequest("hydrology"), "run", 60) == 5
    process.terminate.assert_called_once()


@pytest.mark.parametrize("second_signal", [signal.SIGINT, signal.SIGTERM])
def test_repeated_interrupt_during_cleanup_still_reaps_and_restores_handlers(second_signal):
    process = MagicMock()
    process.is_alive.side_effect = [True, True, False]
    joins = 0

    def interrupt_again(**kwargs):
        nonlocal joins
        joins += 1
        if joins == 1:
            raise KeyboardInterrupt()
        signal.raise_signal(second_signal)

    process.join.side_effect = interrupt_again
    # Safe handlers also make the pre-fix SIGTERM regression non-fatal to pytest.
    previous_term = signal.signal(signal.SIGTERM, jobs._cancel)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        assert jobs.supervise(process, jobs.RefreshRequest("hydrology"), "run", 60) == 5
        process.terminate.assert_called_once()
        process.close.assert_called_once()
        assert signal.getsignal(signal.SIGINT) == previous_int
        assert signal.getsignal(signal.SIGTERM) == jobs._cancel
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def test_validation_precedes_publication_and_preserves_evidence(tmp_path):
    request = jobs.RefreshRequest("hydrology", tmp_path)
    with (
        patch.object(jobs, "source_lock", return_value=nullcontext(MagicMock())),
        patch.object(jobs.hydrology_client, "read_snapshot", side_effect=ValueError("private")),
        patch.object(jobs.hydrology_client, "fetch_snapshot") as fetch,
        patch.object(jobs.hydrology_ingestion, "load_snapshot") as load,
    ):
        with pytest.raises(ValueError):
            jobs.refresh(MagicMock(), request, "run")
        fetch.assert_not_called()
        load.assert_not_called()
        assert tmp_path.is_dir()


def test_worker_failure_has_no_exception_payload(capsys):
    with (
        patch.object(jobs, "IngestionSettings", side_effect=ValueError("private credential")),
        patch.object(jobs.signal, "signal"),
        pytest.raises(SystemExit) as error,
    ):
        jobs._worker(jobs.RefreshRequest("hydrology"), "run")
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "refresh_failed" in output and "ValueError" in output
    assert "private credential" not in output


def test_log_fields_are_allowlisted():
    record = logging.makeLogRecord(
        {
            "msg": "refresh_progress",
            "run_id": "run",
            "source": "hydrology",
            "elapsed_seconds": 30,
            "password": "private",
            "manifest": {"secret": "private"},
        }
    )
    output = json.loads(JsonFormatter().format(record))
    assert output["elapsed_seconds"] == 30 and output["source"] == "hydrology"
    assert "password" not in output and "manifest" not in output
