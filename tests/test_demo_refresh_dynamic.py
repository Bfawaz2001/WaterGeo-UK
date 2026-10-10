from unittest.mock import Mock

import pytest

from watergeo.operations import demo_refresh_dynamic


def test_refreshes_exact_dynamic_portfolio_sequentially() -> None:
    calls: list[str] = []
    messages: list[str] = []

    def refresh(arguments: list[str]) -> int:
        calls.append(arguments[0])
        return 0

    assert demo_refresh_dynamic.run(refresher=refresh, output=messages.append) == 0
    assert calls == list(demo_refresh_dynamic.DYNAMIC_SOURCES)
    assert messages[-2] == "Dynamic refresh summary: 6 accepted, 0 failed, 0 not run."
    assert messages[-1].endswith("not publisher-live guarantees.")


def test_partial_failure_is_visible_and_returns_nonzero() -> None:
    refresh = Mock(side_effect=[0, 1, 3, 4, 0, 0])
    messages: list[str] = []

    assert demo_refresh_dynamic.run(refresher=refresh, output=messages.append) == 1
    assert refresh.call_count == 6
    assert "water-quality: failed" in messages
    assert "thames-discharge-status: busy" in messages
    assert "rainfall: timed out" in messages
    assert messages[-2] == "Dynamic refresh summary: 3 accepted, 3 failed, 0 not run."


def test_interruption_stops_later_refreshes_and_reports_not_run() -> None:
    refresh = Mock(side_effect=[0, 5])
    messages: list[str] = []

    assert demo_refresh_dynamic.run(refresher=refresh, output=messages.append) == 1
    assert refresh.call_count == 2
    assert "water-quality: interrupted" in messages
    assert messages[-2] == "Dynamic refresh summary: 1 accepted, 1 failed, 4 not run."


def test_help_does_not_start_refresh(capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        demo_refresh_dynamic.main(["--help"])
    assert stopped.value.code == 0
    assert "Sequentially refresh" in capsys.readouterr().out
