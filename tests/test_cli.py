"""CLI behavior without network or database access."""

import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from watergeo import cli
from watergeo.client import WaterGeoAPIError, WaterGeoResponseError, WaterGeoTransportError
from watergeo.client.models import Health


class FakeClient:
    def __init__(self, result: object = Health(status="ok")) -> None:
        self.result = result
        self.closed = False

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def health(self) -> object:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def install_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> None:
    real_client = cli.WaterGeoClient

    class ClientFactory(real_client):
        def __new__(cls, *_: object, **__: object) -> FakeClient:
            return fake

    monkeypatch.setattr(cli, "WaterGeoClient", ClientFactory)


def test_health_writes_deterministic_json_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeClient()
    install_fake(monkeypatch, fake)
    assert cli.main(["--base-url", "http://127.0.0.1:8000", "health"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"status":"ok"}\n'
    assert captured.err == ""
    assert fake.closed


def test_pretty_output_is_valid_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_fake(monkeypatch, FakeClient())
    assert cli.main(["--base-url", "http://localhost:8000", "--pretty", "health"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "ok"}
    assert '\n  "status"' in captured.out


@pytest.mark.parametrize(
    "error,exit_code,label",
    [
        (WaterGeoTransportError("request failed"), cli.EXIT_TRANSPORT, "transport error"),
        (WaterGeoAPIError(503, "unavailable"), cli.EXIT_API, "API error"),
        (WaterGeoResponseError("bad response"), cli.EXIT_RESPONSE, "response/configuration"),
    ],
)
def test_expected_failures_use_stderr_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    label: str,
) -> None:
    install_fake(monkeypatch, FakeClient(error))
    assert cli.main(["--base-url", "http://localhost:8000", "health"]) == exit_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert label in captured.err
    assert "Traceback" not in captured.err


def test_base_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATERGEO_BASE_URL", raising=False)
    with pytest.raises(SystemExit) as caught:
        cli.main(["health"])
    assert caught.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    [
        ["sources", "status"],
        ["water-supply", "dataset"],
        ["water-supply", "areas", "--all"],
        ["water-supply", "at-point", "--lon", "-2", "--lat", "52"],
        ["water-supply", "area", "1"],
        ["water-supply", "geometry", "1"],
        ["hydrology", "dataset"],
        ["hydrology", "stations", "--all"],
        ["hydrology", "near", "--lon", "-2", "--lat", "52"],
        ["hydrology", "station", "station-id"],
        ["hydrology", "history", "00000000-0000-4000-8000-000000000001"],
        ["catchments", "dataset"],
        ["catchments", "river-basin-districts", "--id", "1"],
        ["catchments", "management-catchments", "--all"],
        ["catchments", "operational-catchments"],
        ["catchments", "water-bodies"],
        ["catchments", "water-body-geometry", "GB123"],
        ["water-quality", "dataset"],
        ["water-quality", "sampling-points", "--all"],
        ["water-quality", "near", "--lon", "-2", "--lat", "52"],
        ["water-quality", "sampling-point", "AN/CORBY"],
        ["water-quality", "observations", "00000000-0000-4000-8000-000000000001"],
        ["severn-trent", "dataset"],
        ["severn-trent", "reservoirs", "--all"],
        ["severn-trent", "near", "--lon", "-2", "--lat", "52"],
        ["severn-trent", "reservoir", "1"],
        ["severn-trent", "readings", "1", "--all"],
    ],
)
def test_documented_command_surface_parses(arguments: list[str]) -> None:
    parsed = cli.build_parser().parse_args(["--base-url", "http://127.0.0.1:8000", *arguments])
    assert callable(parsed.action)


def test_console_entry_point_is_packaged() -> None:
    pyproject = Path("pyproject.toml").read_text()
    assert 'watergeo = "watergeo.cli:main"' in pyproject


@pytest.mark.parametrize(
    "arguments,method",
    [
        (["hydrology", "stations"], "iter_hydrology_stations"),
        (["catchments", "management-catchments"], "iter_management_catchments"),
        (["water-quality", "sampling-points"], "iter_water_quality_sampling_points"),
        (["severn-trent", "reservoirs"], "iter_reservoirs"),
        (["severn-trent", "readings", "1"], "iter_reservoir_readings"),
    ],
)
def test_all_mode_passes_snapshot_to_iterator(arguments: list[str], method: str) -> None:
    snapshot = "00000000-0000-4000-8000-000000000001"
    parsed = cli.build_parser().parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8000",
            *arguments,
            "--all",
            "--snapshot-id",
            snapshot,
        ]
    )
    client = MagicMock()
    getattr(client, method).return_value = iter(())

    parsed.action(client, parsed)

    assert getattr(client, method).call_args.kwargs["snapshot_id"] == UUID(snapshot)


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["hydrology", "stations", "--all", "--after-id", "A"], "--after-id"),
        (
            [
                "hydrology",
                "history",
                "00000000-0000-4000-8000-000000000001",
                "--all",
                "--after",
                "2026-01-01T00:00:00Z",
            ],
            "--after",
        ),
        (
            [
                "water-quality",
                "observations",
                "00000000-0000-4000-8000-000000000001",
                "--all",
                "--after-id",
                "A",
            ],
            "--after-id",
        ),
        (["severn-trent", "readings", "1", "--all", "--after", "2026-01-01T00:00:00Z"], "--after"),
        (["water-supply", "areas", "--all", "--after-id", "1"], "--after-id"),
    ],
)
def test_all_mode_rejects_manual_cursor(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected: str,
) -> None:
    install_fake(monkeypatch, FakeClient())
    result = cli.main(["--base-url", "http://127.0.0.1:8000", *arguments])
    captured = capsys.readouterr()
    assert result == cli.EXIT_RESPONSE
    assert expected in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    "option",
    [["--snapshot-id", "00000000-0000-4000-8000-000000000001"], ["--after-id", "A"], ["--all"]],
)
def test_catchment_detail_rejects_list_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    option: list[str],
) -> None:
    install_fake(monkeypatch, FakeClient())
    result = cli.main(
        [
            "--base-url",
            "http://127.0.0.1:8000",
            "catchments",
            "management-catchments",
            "--id",
            "1",
            *option,
        ]
    )
    captured = capsys.readouterr()
    assert result == cli.EXIT_RESPONSE
    assert "--id cannot be combined" in captured.err
    assert captured.out == ""


def test_page_bounds_require_all(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_fake(monkeypatch, FakeClient())
    result = cli.main(
        [
            "--base-url",
            "http://127.0.0.1:8000",
            "hydrology",
            "stations",
            "--max-pages",
            "2",
        ]
    )
    captured = capsys.readouterr()
    assert result == cli.EXIT_RESPONSE
    assert "require --all" in captured.err
