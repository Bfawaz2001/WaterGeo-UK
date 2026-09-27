import hashlib
import json
from pathlib import Path

import pytest

from watergeo.fabric_validation import validate_bundle


def fabric_bundle(tmp_path: Path, entity: str = "thames-discharge-status") -> Path:
    directory = tmp_path / "bundle"
    directory.mkdir()
    parquet = f"{entity}.parquet" if entity != "water-supply" else "water-supply.parquet"
    body = b"synthetic parquet"
    (directory / parquet).write_bytes(body)
    manifest = {
        "export_version": "test",
        "entity": entity,
        "dataset": {"snapshot_id": "11111111-1111-4111-8111-111111111111"},
        "files": {parquet: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def test_fabric_preflight_verifies_manifest_snapshot_and_all_files(tmp_path: Path) -> None:
    directory = fabric_bundle(tmp_path)
    manifest = validate_bundle(directory, "thames-discharge-status")
    assert manifest["dataset"]["snapshot_id"] == "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("change", ["checksum", "extra", "symlink", "entity", "snapshot"])
def test_fabric_preflight_fails_closed(tmp_path: Path, change: str) -> None:
    directory = fabric_bundle(tmp_path)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    parquet = directory / "thames-discharge-status.parquet"
    if change == "checksum":
        parquet.write_bytes(b"changed")
    elif change == "extra":
        (directory / "extra.txt").write_text("unexpected")
    elif change == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(parquet.read_bytes())
        parquet.unlink()
        parquet.symlink_to(outside)
    elif change == "entity":
        manifest["entity"] = "unknown"
        manifest_path.write_text(json.dumps(manifest))
    else:
        manifest["dataset"]["snapshot_id"] = "not-a-uuid"
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, KeyError)):
        validate_bundle(directory)
