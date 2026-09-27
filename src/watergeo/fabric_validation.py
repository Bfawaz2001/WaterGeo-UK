"""Offline preflight for a WaterGeo bundle before manual OneLake upload."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

ENTITIES = {
    "water-supply": "water-supply.parquet",
    "thames-discharge-status": "thames-discharge-status.parquet",
}


def validate_bundle(directory: Path, expected_entity: str | None = None) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Bundle must be a real directory")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Bundle manifest is missing or unsafe")
    parsed = json.loads(manifest_path.read_bytes())
    if not isinstance(parsed, dict):
        raise ValueError("Bundle manifest must be a JSON object")
    manifest: dict[str, Any] = parsed
    entity = manifest.get("entity")
    if entity not in ENTITIES or (expected_entity is not None and entity != expected_entity):
        raise ValueError("Unexpected WaterGeo export entity")
    snapshot = str(UUID(manifest["dataset"]["snapshot_id"]))
    if snapshot != manifest["dataset"]["snapshot_id"]:
        raise ValueError("Snapshot identity is not canonical")
    files = manifest.get("files")
    if not isinstance(files, dict) or ENTITIES[entity] not in files:
        raise ValueError("Fabric validation requires the entity GeoParquet file")
    expected_names = {"manifest.json", *files}
    if {path.name for path in directory.iterdir()} != expected_names:
        raise ValueError("Bundle contains unlisted files")
    for name, expected in files.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != expected.get("bytes"):
            raise ValueError("Bundle file size or path mismatch")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected.get("sha256"):
            raise ValueError("Bundle file checksum mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--entity", choices=tuple(ENTITIES))
    args = parser.parse_args()
    manifest = validate_bundle(args.bundle, args.entity)
    print(
        json.dumps(
            {
                "status": "verified",
                "entity": manifest["entity"],
                "snapshot_id": manifest["dataset"]["snapshot_id"],
                "file_count": len(manifest["files"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
