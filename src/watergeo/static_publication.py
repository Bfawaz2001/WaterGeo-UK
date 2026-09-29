"""Build an immutable, deterministic static WaterGeo publication from the reviewed API."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import httpx2 as httpx
from shapely.geometry import shape

PUBLICATION_VERSION = "watergeo-static-publication-v1"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class StaticPublicationError(ValueError):
    """The API could not produce one complete static publication."""


class ApiReader:
    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise StaticPublicationError("Static publication API must be a local build service")
        self.client = httpx.Client(
            base_url=self.base_url, transport=transport, trust_env=False, timeout=120
        )

    def close(self) -> None:
        self.client.close()

    def get(self, path: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path + (f"?{urlencode(parameters)}" if parameters else "")
        response = self.client.get(url, follow_redirects=False)
        if response.status_code != 200:
            raise StaticPublicationError(f"Required API product unavailable: {path}")
        if response.headers.get("content-type", "").split(";")[0] not in {
            "application/json",
            "application/geo+json",
        }:
            raise StaticPublicationError("Unexpected API response type")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise StaticPublicationError("API response exceeded static publication budget")
        value = response.json()
        if not isinstance(value, dict):
            raise StaticPublicationError("Invalid API response")
        return value


def _snapshot(page: dict[str, Any]) -> str:
    dataset = page.get("dataset")
    if not isinstance(dataset, dict):
        raise StaticPublicationError("Static source omitted snapshot provenance")
    _validate_dataset(dataset)
    return cast(str, dataset["snapshot_id"])


def _validate_dataset(dataset: dict[str, Any]) -> None:
    required = ("snapshot_id", "publisher", "attribution")
    if not all(isinstance(dataset.get(field), str) and dataset[field] for field in required):
        raise StaticPublicationError("Static source omitted required provenance")
    if not isinstance(dataset.get("licence") or dataset.get("licence_name"), str):
        raise StaticPublicationError("Static source omitted licence provenance")
    if not isinstance(dataset.get("retrieval_completed_at") or dataset.get("retrieved_at"), str):
        raise StaticPublicationError("Static source omitted retrieval provenance")
    if not isinstance(
        dataset.get("normalization_version") or dataset.get("transformation_version"), str
    ):
        raise StaticPublicationError("Static source omitted source version")


def pages(
    api: ApiReader,
    path: str,
    *,
    identity: str,
    snapshot: str | None = None,
    next_name: str = "next_after_id",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    after: str | int | None = None
    dataset: dict[str, Any] | None = None
    for _ in range(200):
        parameters: dict[str, Any] = {"limit": 100}
        if snapshot:
            parameters["snapshot_id"] = snapshot
        if after is not None:
            parameters["after_id"] = after
        page = api.get(path, parameters)
        current = _snapshot(page)
        if snapshot is None:
            snapshot = current
        if current != snapshot:
            raise StaticPublicationError("API snapshot changed during static publication")
        if dataset is None:
            dataset = page["dataset"]
        batch = page.get("items")
        if not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch):
            raise StaticPublicationError("Invalid static publication page")
        items.extend(batch)
        after = page.get(next_name)
        if after is None:
            break
        if not batch or batch[-1].get(identity) != after:
            raise StaticPublicationError("Invalid static publication cursor")
    else:
        raise StaticPublicationError("Static publication page budget exceeded")
    if dataset is None:
        raise StaticPublicationError("Empty static publication response")
    return dataset, items


def feature_collection(items: list[dict[str, Any]], identity: str) -> dict[str, Any]:
    features = []
    for item in items:
        geometry = item.get("geometry")
        if geometry is None and isinstance(item.get("longitude"), (int, float)):
            geometry = {
                "type": "Point",
                "coordinates": [item["longitude"], item["latitude"]],
            }
        if not isinstance(geometry, dict):
            continue
        features.append(
            {
                "type": "Feature",
                "id": item[identity],
                "geometry": geometry,
                "properties": {key: value for key, value in item.items() if key != "geometry"},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _write(staging: Path, relative: str, value: Any) -> dict[str, Any]:
    path = staging / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    body = encode(value)
    path.write_bytes(body)
    count = None
    if isinstance(value, dict):
        collection = value.get("features", value.get("items"))
        if isinstance(collection, list):
            count = len(collection)
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "count": count}


def _point_product(
    api: ApiReader,
    staging: Path,
    directory: str,
    endpoint: str,
    identity: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset, items = pages(api, endpoint, identity=identity)
    files = {
        f"datasets/{directory}/items.json": _write(
            staging, f"datasets/{directory}/items.json", {"dataset": dataset, "items": items}
        ),
        f"datasets/{directory}/items.geojson": _write(
            staging, f"datasets/{directory}/items.geojson", feature_collection(items, identity)
        ),
    }
    return dataset, files


def _write_geoparquet(
    staging: Path,
    relative: str,
    dataset: dict[str, Any],
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        {
            "source_id": str(feature["id"]),
            "snapshot_id": dataset["snapshot_id"],
            "publisher": dataset["publisher"],
            "retrieved_at": dataset.get("retrieval_completed_at") or dataset.get("retrieved_at"),
            "licence": dataset.get("licence") or dataset.get("licence_name"),
            "properties_json": encode(feature.get("properties", {})).decode(),
            "geometry": shape(feature["geometry"]).wkb,
        }
        for feature in features
    ]
    schema = pa.schema(
        [
            ("source_id", pa.string()),
            ("snapshot_id", pa.string()),
            ("publisher", pa.string()),
            ("retrieved_at", pa.string()),
            ("licence", pa.string()),
            ("properties_json", pa.string()),
            ("geometry", pa.binary()),
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    geometry_types = sorted({feature["geometry"]["type"] for feature in features})
    geo = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {"geometry": {"encoding": "WKB", "geometry_types": geometry_types}},
    }
    table = table.replace_schema_metadata(
        {
            b"geo": encode(geo),
            b"watergeo": encode({"publication_version": PUBLICATION_VERSION, "dataset": dataset}),
        }
    )
    path = staging / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "count": len(rows)}


def _write_analytics(
    staging: Path, datasets: dict[str, dict[str, Any]], files: dict[str, Any]
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    for directory in ("rainfall", "bathing-waters"):
        collection = json.loads((staging / f"datasets/{directory}/items.geojson").read_text())
        relative = f"analytics/{directory}.parquet"
        files[relative] = _write_geoparquet(
            staging, relative, datasets[directory], collection["features"]
        )
    flood = json.loads((staging / "datasets/flood-warnings/areas.geojson").read_text())
    files["analytics/flood-areas.parquet"] = _write_geoparquet(
        staging,
        "analytics/flood-areas.parquet",
        datasets["flood-warnings"],
        flood["features"],
    )
    performance = json.loads((staging / "datasets/company-performance/companies.json").read_text())
    rows = [
        {
            "snapshot_id": datasets["company-performance"]["snapshot_id"],
            "publisher": datasets["company-performance"]["publisher"],
            "retrieved_at": datasets["company-performance"]["retrieval_completed_at"],
            "licence": datasets["company-performance"]["licence"],
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "boundary_company_acronym": company.get("boundary_company_acronym"),
            **measure,
        }
        for company in performance["items"]
        for measure in company["measures"]
    ]
    table = pa.Table.from_pylist(rows).replace_schema_metadata(
        {
            b"watergeo": encode(
                {
                    "publication_version": PUBLICATION_VERSION,
                    "dataset": datasets["company-performance"],
                }
            )
        }
    )
    path = staging / "analytics/company-performance.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    body = path.read_bytes()
    files["analytics/company-performance.parquet"] = {
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "count": len(rows),
    }


def build_publication(
    api: ApiReader, destination: Path, commit: str, *, analytics: bool = False
) -> dict[str, Any]:
    if destination.exists():
        raise StaticPublicationError("Publication destination already exists")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise StaticPublicationError("WaterGeo commit must be a full lowercase SHA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watergeo-static-", dir=destination.parent) as temp:
        staging = Path(temp) / "watergeo-data"
        staging.mkdir()
        files: dict[str, Any] = {}
        datasets: dict[str, dict[str, Any]] = {}
        specifications = (
            ("hydrology", "/v1/hydrology/stations", "station_id"),
            ("water-quality", "/v1/water-quality/sampling-points", "sampling_point_id"),
            (
                "reservoir-levels",
                "/v1/severn-trent/reservoir-levels/reservoirs",
                "reservoir_id",
            ),
            (
                "thames-discharge",
                "/v1/thames-water/discharge-status/sites",
                "site_id",
            ),
            ("rainfall", "/v1/rainfall/stations", "station_id"),
            ("bathing-waters", "/v1/bathing-waters", "bathing_water_id"),
        )
        search: list[dict[str, Any]] = []
        for directory, endpoint, identity in specifications:
            dataset, produced = _point_product(api, staging, directory, endpoint, identity)
            datasets[directory] = dataset
            files.update(produced)
            payload = json.loads((staging / f"datasets/{directory}/items.json").read_text())
            for item in payload["items"]:
                label = (
                    item.get("display_name")
                    or item.get("name")
                    or item.get("location_name")
                    or item.get("pref_label")
                    or (item.get("labels") or [None])[0]
                    or item[identity]
                )
                search.append(
                    {
                        "kind": directory,
                        "identity": item[identity],
                        "label": label,
                        "context": directory.replace("-", " "),
                        "publisher": dataset["publisher"],
                        "longitude": item.get("longitude"),
                        "latitude": item.get("latitude"),
                        "snapshot_id": dataset["snapshot_id"],
                    }
                )

        catchment_dataset, water_bodies = pages(
            api, "/v1/catchments/water-bodies", identity="water_body_id"
        )
        datasets["catchments"] = catchment_dataset
        files["datasets/catchments/water-bodies.json"] = _write(
            staging,
            "datasets/catchments/water-bodies.json",
            {"dataset": catchment_dataset, "items": water_bodies},
        )
        water_body_features: list[dict[str, Any]] = []
        for water_body in water_bodies:
            geometry = api.get(
                f"/v1/catchments/water-bodies/{water_body['water_body_id']}/geometry",
                {"snapshot_id": catchment_dataset["snapshot_id"]},
            )
            if geometry.get("snapshot_id") != catchment_dataset["snapshot_id"]:
                raise StaticPublicationError("Catchment snapshot changed during publication")
            for feature in geometry.get("features", []):
                properties = dict(feature.get("properties") or {})
                properties["water_body_id"] = water_body["water_body_id"]
                water_body_features.append({**feature, "properties": properties})
        files["datasets/catchments/water-bodies.geojson"] = _write(
            staging,
            "datasets/catchments/water-bodies.geojson",
            {"type": "FeatureCollection", "features": water_body_features},
        )
        for water_body in water_bodies:
            search.append(
                {
                    "kind": "water-body",
                    "identity": water_body["water_body_id"],
                    "label": water_body["name"],
                    "context": water_body.get("water_body_type") or "Water Body",
                    "publisher": catchment_dataset["publisher"],
                    "longitude": None,
                    "latitude": None,
                    "snapshot_id": catchment_dataset["snapshot_id"],
                }
            )
        flood_dataset = api.get("/v1/flood-monitoring/dataset")
        _validate_dataset(flood_dataset)
        flood_page = api.get(
            "/v1/flood-monitoring/areas",
            {"snapshot_id": flood_dataset["snapshot_id"]},
        )
        datasets["flood-warnings"] = flood_dataset
        files["datasets/flood-warnings/areas.geojson"] = _write(
            staging,
            "datasets/flood-warnings/areas.geojson",
            feature_collection(flood_page["items"], "area_id"),
        )
        for area in flood_page["items"]:
            search.append(
                {
                    "kind": "flood-warnings",
                    "identity": area["area_id"],
                    "label": area["label"],
                    "context": area.get("county") or "Flood area",
                    "publisher": flood_dataset["publisher"],
                    "longitude": None,
                    "latitude": None,
                    "snapshot_id": flood_dataset["snapshot_id"],
                }
            )
        performance = api.get("/v1/company-performance/dataset")
        _validate_dataset(performance)
        companies = api.get(
            "/v1/company-performance/companies",
            {"snapshot_id": performance["snapshot_id"]},
        )
        company_details = [
            api.get(
                f"/v1/company-performance/companies/{company['company_id']}",
                {"snapshot_id": performance["snapshot_id"]},
            )["item"]
            for company in companies["items"]
        ]
        datasets["company-performance"] = performance
        files["datasets/company-performance/companies.json"] = _write(
            staging,
            "datasets/company-performance/companies.json",
            {"dataset": performance, "items": company_details},
        )

        supply = api.get("/v1/water-supply/dataset")
        _validate_dataset(supply)
        areas: list[dict[str, Any]] = []
        after: int | None = None
        for _ in range(20):
            parameters = {"limit": 100, **({"after_id": after} if after else {})}
            page = api.get("/v1/water-supply/areas", parameters)
            if page.get("snapshot_id") != supply["snapshot_id"]:
                raise StaticPublicationError("Water-supply snapshot changed")
            areas.extend(page["items"])
            after = page.get("next_after_id")
            if after is None:
                break
        if len(areas) != supply["area_count"]:
            raise StaticPublicationError("Incomplete water-supply static publication")
        datasets["water-supply"] = supply
        files["datasets/water-supply/areas.json"] = _write(
            staging, "datasets/water-supply/areas.json", {"dataset": supply, "items": areas}
        )
        for area in areas:
            relative = f"datasets/water-supply/areas/{area['source_id']}.geojson"
            files[relative] = _write(
                staging, relative, api.get(f"/v1/water-supply/areas/{area['source_id']}/geometry")
            )
            search.append(
                {
                    "kind": "water-supply",
                    "identity": str(area["source_id"]),
                    "label": area.get("company")
                    or area.get("area_served")
                    or f"Area {area['source_id']}",
                    "context": area.get("area_served") or "Water-supply area",
                    "publisher": supply["publisher"],
                    "longitude": None,
                    "latitude": None,
                    "snapshot_id": supply["snapshot_id"],
                }
            )

        if analytics:
            _write_analytics(staging, datasets, files)

        statuses = api.get("/v1/sources/status")
        retrievals = [
            value
            for dataset in datasets.values()
            if isinstance(
                (value := dataset.get("retrieval_completed_at") or dataset.get("retrieved_at")),
                str,
            )
        ]
        generated_at = max(retrievals)
        statuses["checked_at"] = generated_at
        files["source-status.json"] = _write(staging, "source-status.json", statuses)
        search.sort(key=lambda row: (str(row["label"]).casefold(), row["kind"], row["identity"]))
        files["search-index.json"] = _write(
            staging, "search-index.json", {"generated_at": generated_at, "items": search}
        )
        identity_material = {
            "version": PUBLICATION_VERSION,
            "commit": commit,
            "sources": {name: value["snapshot_id"] for name, value in sorted(datasets.items())},
            "files": {name: metadata["sha256"] for name, metadata in sorted(files.items())},
        }
        publication_id = hashlib.sha256(encode(identity_material)).hexdigest()
        manifest = {
            "publication_version": PUBLICATION_VERSION,
            "publication_id": publication_id,
            "generated_at": generated_at,
            "watergeo_commit": commit,
            "data_mode": "static_snapshot",
            "sources": datasets,
            "files": dict(sorted(files.items())),
            "caveats": [
                "Static publication times differ from publisher observation times.",
                "Static browser filtering is bounded to this immutable accepted snapshot.",
                "WaterGeo is not an emergency flood-warning or bathing-safety service.",
            ],
        }
        (staging / "manifest.json").write_bytes(encode(manifest))
        shutil.move(staging, destination)
    return manifest


def current_commit() -> str:
    result = subprocess.run(
        ("/usr/bin/git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", default=None)
    parser.add_argument(
        "--analytics", action="store_true", help="Write optional GeoParquet/Parquet outputs"
    )
    arguments = parser.parse_args(argv)
    api = ApiReader(arguments.api_url)
    try:
        manifest = build_publication(
            api,
            arguments.output,
            arguments.commit or current_commit(),
            analytics=arguments.analytics,
        )
    finally:
        api.close()
    print(
        json.dumps({"publication_id": manifest["publication_id"], "output": str(arguments.output)})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
