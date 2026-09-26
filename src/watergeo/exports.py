"""Portable, snapshot-verified presentation exports; no provider credentials required."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from watergeo.client import WaterGeoClient

EXPORT_VERSION = "watergeo-export-v1"
TILE_LAYER = "water_supply"


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def collect_supply(client: WaterGeoClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Use only API-reviewed WGS84 geometry; fail closed across snapshot changes."""
    dataset = client.water_supply_dataset().model_dump(mode="json")
    features = []
    for area in client.iter_water_supply_areas(max_records=2000, max_pages=20):
        feature = client.water_supply_geometry(area.source_id).model_dump(mode="json")
        if feature["properties"]["snapshot_id"] != dataset["snapshot_id"]:
            raise ValueError("Water-supply snapshot changed during export")
        if feature["presentation"]["policy_version"] != dataset["presentation_version"]:
            raise ValueError("Water-supply presentation policy changed during export")
        features.append(feature)
    if len(features) != dataset["area_count"]:
        raise ValueError("Incomplete water-supply export")
    if client.water_supply_dataset().model_dump(mode="json") != dataset:
        raise ValueError("Water-supply dataset changed during export")
    return dataset, features


def write_parquet(
    destination: Path, dataset: dict[str, Any], features: list[dict[str, Any]]
) -> None:
    """GeoParquet 1.1 WKB, longitude/latitude CRS84; source fields retained as JSON."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        {
            "source_id": str(feature["id"]),
            "snapshot_id": dataset["snapshot_id"],
            "company": feature["properties"].get("company"),
            "publisher": dataset["publisher"],
            "licence": dataset["licence_name"],
            "attribution": dataset["attribution"],
            "presentation_version": dataset["presentation_version"],
            "properties_json": encode(feature["properties"]).decode(),
            "presentation_json": encode(feature["presentation"]).decode(),
            "geometry": shape(feature["geometry"]).wkb,
        }
        for feature in features
    ]
    schema = pa.schema(
        [(key, pa.binary() if key == "geometry" else pa.string()) for key in rows[0]]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    metadata = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["MultiPolygon"]}},
    }
    table = table.replace_schema_metadata(
        {
            b"geo": encode(metadata),
            b"watergeo": encode({"export_version": EXPORT_VERSION, "dataset": dataset}),
        }
    )
    pq.write_table(table, destination, compression="zstd")


def build_export(
    client: WaterGeoClient,
    destination: Path,
    *,
    parquet: bool = False,
    tippecanoe: str | None = None,
) -> dict[str, Any]:
    """Publish a new directory only after all files succeed; never replace existing exports."""
    if destination.exists():
        raise ValueError("Export destination already exists; use a new version directory")
    dataset, features = collect_supply(client)
    if not features:
        raise ValueError("Cannot export an empty snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watergeo-export-", dir=destination.parent) as temp:
        staging = Path(temp) / "bundle"
        staging.mkdir()
        geojson = staging / "water-supply.geojson"
        geojson.write_bytes(encode({"type": "FeatureCollection", "features": features}))
        manifest: dict[str, Any] = {
            "export_version": EXPORT_VERSION,
            "entity": "water-supply",
            "dataset": dataset,
            "feature_count": len(features),
            "coordinate_reference": "OGC:CRS84",
            "files": {},
        }
        if parquet:
            write_parquet(staging / "water-supply.parquet", dataset, features)
        if tippecanoe:
            executable = shutil.which(tippecanoe)
            if executable is None:
                raise ValueError("Tippecanoe executable was not found")
            version = subprocess.run(  # noqa: S603
                [executable, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            # Input is the reviewed API output. Tiling simplifies/clips ONLY this derivative.
            arguments = [
                "--quiet",
                "-Z0",
                "-z8",
                "--name=WaterGeo water-supply overview",
                "--description=Presentation derivative; exact geometry through WaterGeo API",
                "--no-feature-limit",
                "--no-tile-size-limit",
                "--no-tiny-polygon-reduction",
                "--layer=" + TILE_LAYER,
                "--include=source_id",
                "--include=company",
                "--include=snapshot_id",
                "--attribution=" + dataset["attribution"],
                "--output=water-supply.pmtiles",
                "water-supply.geojson",
            ]
            subprocess.run(  # noqa: S603
                ["tippecanoe", *arguments],  # noqa: S607 -- resolved executable is passed explicitly
                executable=executable,
                cwd=staging,
                check=True,
                timeout=1800,
            )
            manifest["tiles"] = {
                "layer": TILE_LAYER,
                "minzoom": 0,
                "maxzoom": 8,
                "tool": (version.stdout + version.stderr).strip(),
                "policy": "overview-v1; clipped, quantized and simplified; never for analysis",
                "source_geojson_sha256": hashlib.sha256(geojson.read_bytes()).hexdigest(),
            }
        for file in sorted(staging.iterdir()):
            manifest["files"][file.name] = {
                "bytes": file.stat().st_size,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        (staging / "manifest.json").write_bytes(encode(manifest))
        staging.rename(destination)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="WaterGeo HTTP API URL")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--parquet", action="store_true", help="Requires the exports extra")
    parser.add_argument("--tippecanoe", help="Optional executable path to build overview PMTiles")
    args = parser.parse_args()
    with WaterGeoClient(args.base_url) as client:
        build_export(client, args.output, parquet=args.parquet, tippecanoe=args.tippecanoe)


if __name__ == "__main__":
    main()
