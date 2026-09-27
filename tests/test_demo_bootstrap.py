from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

from watergeo.api.source_models import SourceStatus
from watergeo.operations import demo_bootstrap


def status(source: demo_bootstrap.DemoSource, available: bool) -> SourceStatus:
    semantics = {
        "ofwat": "versioned_release",
        "catchments": "versioned_plan",
        "stream-reservoir-levels": "versioned_release",
    }.get(source, "dynamic_snapshot")
    return SourceStatus(
        source=source,
        semantics=semantics,
        availability="available" if available else "unavailable",
        normalization_version="test",
        retrieved_at=datetime.now(UTC) if available else None,
        retrieval_freshness="current" if available else "unknown",
        caveat="Test source.",
    )


def test_bootstrap_replays_missing_evidence_and_preserves_loaded_source(
    tmp_path: Path, monkeypatch
) -> None:
    retained = tmp_path / "raw" / "environment-agency" / "hydrology" / "bundle"
    retained.mkdir(parents=True)
    states = iter(
        (
            {"ofwat": status("ofwat", True), "hydrology": status("hydrology", False)},
            {"ofwat": status("ofwat", True), "hydrology": status("hydrology", True)},
        )
    )
    monkeypatch.setattr(demo_bootstrap, "database_is_ready", lambda engine: True)
    monkeypatch.setattr(demo_bootstrap, "status_map", lambda engine, settings: next(states))
    refresh = Mock(return_value=0)

    result = demo_bootstrap.run(
        ("ofwat", "hydrology"),
        status_only=False,
        dry_run=False,
        offline=True,
        engine=Mock(),
        settings=Mock(),
        refresher=refresh,
        data_root=tmp_path,
    )

    assert result == 0
    refresh.assert_called_once_with(
        ["hydrology", "--timeout-seconds", "3600", "--evidence-dir", str(retained.resolve())]
    )


def test_offline_bootstrap_continues_independent_sources_and_fails_target(
    tmp_path: Path, monkeypatch
) -> None:
    missing = {
        "hydrology": status("hydrology", False),
        "thames-discharge-status": status("thames-discharge-status", False),
    }
    monkeypatch.setattr(demo_bootstrap, "database_is_ready", lambda engine: True)
    monkeypatch.setattr(demo_bootstrap, "status_map", lambda engine, settings: missing)
    assert (
        demo_bootstrap.run(
            ("hydrology", "thames-discharge-status"),
            status_only=False,
            dry_run=False,
            offline=True,
            engine=Mock(),
            settings=Mock(),
            data_root=tmp_path,
        )
        == 1
    )


def test_status_mode_does_not_refresh(monkeypatch) -> None:
    statuses = {"water-quality": status("water-quality", True)}
    monkeypatch.setattr(demo_bootstrap, "database_is_ready", lambda engine: True)
    monkeypatch.setattr(demo_bootstrap, "status_map", lambda engine, settings: statuses)
    refresh = Mock()
    assert (
        demo_bootstrap.run(
            ("water-quality",),
            status_only=True,
            dry_run=False,
            offline=False,
            engine=Mock(),
            settings=Mock(),
            refresher=refresh,
        )
        == 0
    )
    refresh.assert_not_called()
