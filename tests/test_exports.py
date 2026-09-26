import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from watergeo.client import WaterGeoClient
from watergeo.exports import build_export


def export_client() -> Mock:
    client = Mock(spec=WaterGeoClient)
    dataset = {
        "snapshot_id": "11111111-1111-4111-8111-111111111111",
        "presentation_version": "reviewed-v1",
        "area_count": 1,
        "publisher": "Test publisher",
        "licence_name": "Test licence",
        "attribution": "Test attribution",
        "source_sha256": "a" * 64,
    }
    feature = {
        "type": "Feature",
        "id": 3,
        "properties": {"snapshot_id": dataset["snapshot_id"], "source_id": 3, "company": "Test"},
        "presentation": {"policy_version": "reviewed-v1", "geometry_geojson_sha256": "b" * 64},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [-1, 52],
                        [-1, 53],
                        [0, 53],
                        [-1, 52],
                    ]
                ]
            ],
        },
    }
    client.water_supply_dataset.return_value.model_dump.return_value = dataset
    client.iter_water_supply_areas.return_value = [Mock(source_id=3)]
    client.water_supply_geometry.return_value.model_dump.return_value = feature
    return client


def test_export_preserves_reviewed_geometry_and_hashed_provenance(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot"
    manifest = build_export(export_client(), destination)
    feature = json.loads((destination / "water-supply.geojson").read_bytes())["features"][0]
    assert feature["presentation"]["policy_version"] == "reviewed-v1"
    assert feature["properties"]["snapshot_id"] == manifest["dataset"]["snapshot_id"]
    assert (
        manifest["files"]["water-supply.geojson"]["sha256"]
        == hashlib.sha256((destination / "water-supply.geojson").read_bytes()).hexdigest()
    )
    assert json.loads((destination / "manifest.json").read_bytes()) == manifest
    with pytest.raises(ValueError, match="already exists"):
        build_export(export_client(), destination)


@pytest.mark.parametrize("change", ["snapshot", "policy", "count", "final"])
def test_failed_export_never_publishes_mixed_bundle(tmp_path: Path, change: str) -> None:
    client = export_client()
    dataset = client.water_supply_dataset.return_value.model_dump.return_value
    feature = client.water_supply_geometry.return_value.model_dump.return_value
    if change == "snapshot":
        feature["properties"]["snapshot_id"] = "different"
    elif change == "policy":
        feature["presentation"]["policy_version"] = "different"
    elif change == "count":
        dataset["area_count"] = 2
    else:
        client.water_supply_dataset.return_value.model_dump.side_effect = [
            dataset,
            {**dataset, "snapshot_id": "different"},
        ]
    with pytest.raises(ValueError):
        build_export(client, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_geoparquet_metadata_and_wkb_roundtrip(tmp_path: Path) -> None:
    pq = pytest.importorskip("pyarrow.parquet")
    from shapely import from_wkb

    build_export(export_client(), tmp_path / "snapshot", parquet=True)
    table = pq.read_table(tmp_path / "snapshot" / "water-supply.parquet")
    metadata = table.schema.metadata
    assert json.loads(metadata[b"geo"])["columns"]["geometry"]["encoding"] == "WKB"
    assert json.loads(metadata[b"watergeo"])["dataset"]["attribution"] == "Test attribution"
    assert table.to_pylist()[0]["source_id"] == "3"
    assert from_wkb(table.to_pylist()[0]["geometry"]).is_valid


def test_missing_tile_builder_does_not_publish(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="executable"):
        build_export(export_client(), tmp_path / "snapshot", tippecanoe="missing-watergeo-tool")
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("field", ["snapshot_id", "policy_version"])
def test_tiles_are_not_built_from_mixed_features(tmp_path: Path, field: str) -> None:
    client = export_client()
    client.water_supply_dataset.return_value.model_dump.return_value["area_count"] = 2
    first = client.water_supply_geometry.return_value.model_dump.return_value
    second = deepcopy(first)
    second["id"] = second["properties"]["source_id"] = 4
    second["properties" if field == "snapshot_id" else "presentation"][field] = "changed"
    client.iter_water_supply_areas.return_value = [Mock(source_id=3), Mock(source_id=4)]
    client.water_supply_geometry.return_value.model_dump.side_effect = [first, second]
    with pytest.raises(ValueError, match="changed"):
        build_export(client, tmp_path / "snapshot", tippecanoe="unused-builder")
    assert not (tmp_path / "snapshot").exists()


def test_tile_builder_uses_portable_paths_and_manifest_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from watergeo import exports

    executable = str(tmp_path / "local-tool" / "tippecanoe")
    monkeypatch.setattr(exports.shutil, "which", lambda _: executable)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "tippecanoe test", ""))

    def build(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "cwd" in kwargs:
            staging = Path(str(kwargs["cwd"]))
            assert (staging / "water-supply.geojson").is_file()
            (staging / "water-supply.pmtiles").write_bytes(b"test archive")
        return subprocess.CompletedProcess([], 0, "tippecanoe test", "")

    run.side_effect = build
    monkeypatch.setattr(exports.subprocess, "run", run)
    manifest = build_export(export_client(), tmp_path / "snapshot", tippecanoe=executable)
    invocation = run.call_args
    assert invocation.kwargs["executable"] == executable
    assert invocation.args[0][0] == "tippecanoe"
    assert invocation.args[0][-1] == "water-supply.geojson"
    assert "--output=water-supply.pmtiles" in invocation.args[0]
    assert str(tmp_path) not in " ".join(invocation.args[0])
    assert (
        manifest["tiles"]["source_geojson_sha256"]
        == manifest["files"]["water-supply.geojson"]["sha256"]
    )
    assert (
        manifest["files"]["water-supply.pmtiles"]["sha256"]
        == hashlib.sha256(b"test archive").hexdigest()
    )
