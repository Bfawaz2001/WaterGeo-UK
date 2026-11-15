"""Portable Ofwat publisher-feature product, independent of a database or tenant.

This is a source-preserving analytical product. Invalid publisher features remain
in the product with explicit quarantine flags; no repair policy is inferred.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import shapefile
import shapely
from pyproj import CRS, Transformer, __proj_version__
from shapely.geometry import mapping, shape
from shapely.ops import transform
from shapely.validation import explain_validity

from watergeo.exports import encode
from watergeo.ingestion.ofwat_boundaries import (
    OFWAT_SEWERAGE_V1_5,
    OFWAT_WATER_SUPPLY_V1_5,
    BoundarySource,
    fetch_boundary_source,
)
from watergeo.ingestion.ofwat_boundary_validation import (
    OFWAT_SEWERAGE_V1_5_CONTRACT,
    OFWAT_WATER_SUPPLY_V1_5_CONTRACT,
    BoundaryValidationContract,
    validate_boundary_archive,
)
from watergeo.ingestion.ofwat_canonical import (
    LICENCE_URL,
    SOURCE_LICENCE_STATEMENT,
    _validate_publisher_fields,
)

PRODUCT_VERSION = "watergeo-ofwat-services-v1"
SERVICES = {
    "water-supply": (OFWAT_WATER_SUPPLY_V1_5, OFWAT_WATER_SUPPLY_V1_5_CONTRACT),
    "sewerage": (OFWAT_SEWERAGE_V1_5, OFWAT_SEWERAGE_V1_5_CONTRACT),
}
REVIEW = "docs/data-sources/ofwat-service-company-crosswalk.json"


def digest_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def boundary_id(dataset: str, snapshot: str, source_id: int) -> str:
    """No ID continuity across services or snapshots is assumed."""
    return f"{dataset}:{snapshot}:{source_id}"


def read_crosswalk(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    document = json.loads(path.read_text())
    if document["review_status"] != "reviewed_publisher_label_grouping":
        raise ValueError("Company crosswalk is not reviewed")
    result = {}
    for row in document["mappings"]:
        key = (row["dataset"], row["COMPANY"], row["Acronym"])
        if key in result or not row["company_id"] or not row["review_reference"]:
            raise ValueError("Duplicate or unreviewed company mapping")
        result[key] = row
    return result


def _source_manifest(root: Path, source: BoundarySource) -> dict[str, Any]:
    path = root / f"{source.expected_sha256}.json"
    manifest: dict[str, Any] = json.loads(path.read_text())
    for key in ("dataset", "release", "source_url", "publisher", "distributor", "licence_name"):
        if manifest.get(key) != getattr(source, key):
            raise ValueError(f"Retrieval metadata mismatch: {key}")
    if (
        manifest.get("sha256") != source.expected_sha256
        or manifest.get("bytes") != source.expected_bytes
        or manifest.get("licence_version") is not None
    ):
        raise ValueError("Retrieval identity or licence metadata mismatch")
    return manifest


def decode_service(
    service: str,
    root: Path,
    crosswalk: dict[tuple[str, str, str], dict[str, str]],
    *,
    source: BoundarySource | None = None,
    contract: BoundaryValidationContract | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Verify exact source, preserve WKB, and explicitly label every derivative."""
    selected_source, selected_contract = SERVICES[service]
    source = source or selected_source
    contract = contract or selected_contract
    manifest = _source_manifest(root, source)
    archive = root / f"{source.expected_sha256}.zip"
    if archive.stat().st_size != source.expected_bytes:
        raise ValueError("Source byte count changed")
    validation = validate_boundary_archive(archive, contract=contract)
    projection = Transformer.from_crs(27700, 4326, always_xy=True, allow_ballpark=False)
    rows, features = [], []
    with (
        zipfile.ZipFile(archive) as zipped,
        shapefile.Reader(
            **{
                ext: io.BytesIO(zipped.read(f"{source.expected_basename}.{ext}"))
                for ext in ("shp", "shx", "dbf")
            },
            encoding="utf-8",
            encodingErrors="strict",
        ) as reader,
    ):
        for item in reader.iterShapeRecords():
            fields = {
                key: value.isoformat() if isinstance(value, date) else value
                for key, value in item.record.as_dict().items()
            }
            identifier = int(fields["ID"])
            _validate_publisher_fields(identifier, fields)
            if fields["Created"] != "2020-08-04" or fields["LastUpdate"] != "2024-04-25":
                raise ValueError("Publisher dates changed")
            key = (source.dataset, fields["COMPANY"], fields["Acronym"])
            if key not in crosswalk:
                raise ValueError(f"Missing reviewed company mapping: {key}")
            company = crosswalk[key]
            geometry = shape(item.shape.__geo_interface__)
            wkb = shapely.to_wkb(geometry, byte_order=1, include_srid=False)
            projected = transform(projection.transform, geometry)
            identity = boundary_id(source.dataset, source.expected_sha256, identifier)
            properties = {
                "boundary_id": identity,
                "dataset": source.dataset,
                "snapshot_sha256": source.expected_sha256,
                "service": service,
                "source_id": identifier,
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                **{
                    key: fields[key]
                    for key in (
                        "COMPANY",
                        "Acronym",
                        "CoType",
                        "AreaType",
                        "AreaServed",
                        "WARNINGS",
                    )
                },
                "source_valid": bool(geometry.is_valid),
                "source_validity": explain_validity(geometry),
                "coverage_eligible": bool(geometry.is_valid),
                "presentation_valid": bool(projected.is_valid),
                "presentation_wkb_sha256": hashlib.sha256(
                    shapely.to_wkb(projected, byte_order=1, include_srid=False)
                ).hexdigest(),
                "source_geometry_policy": "publisher-decoded-v1-no-repair",
                "presentation_policy": "reprojected-source-v1-no-repair",
                "source_wkb_sha256": hashlib.sha256(wkb).hexdigest(),
                "licence_name": source.licence_name,
                "licence_version": None,
                "licence_statement": fields["Licence"],
                "source_fields_json": encode(fields).decode(),
                "mapping_review": company["review_reference"],
            }
            rows.append({**properties, "geometry": wkb})
            features.append(
                {
                    "type": "Feature",
                    "id": identity,
                    "properties": properties,
                    "geometry": mapping(projected),
                }
            )
    # Recheck after reading to detect source replacement during export.
    if digest_file(archive) != source.expected_sha256 or _source_manifest(root, source) != manifest:
        raise ValueError("Source snapshot changed during export")
    metadata = {
        **manifest,
        "service": service,
        "validation": validation.to_dict(),
        "attribution": (
            f"Ofwat {service} boundaries, April 2024, {source.release}; distributed by "
            "House of Commons Library; digitised by Ofwat with Ordnance Survey support. "
            "Contains public sector information licensed under the Open Government Licence "
            "(edition not specified by source)."
        ),
        "licence_url": LICENCE_URL,
        "geometry_policy": "publisher-source-v1; original features; no repair or dissolve",
        "invalid_policy": "retained with coverage_eligible=false; no coverage analysis",
        "source_crs": "EPSG:27700",
        "presentation_crs": "OGC:CRS84",
        "projection": projection.description,
        "presentation_invalid_ids": [
            f["properties"]["source_id"]
            for f in features
            if not f["properties"]["presentation_valid"]
        ],
    }
    return metadata, rows, features


def _write_table(path: Path, rows: list[dict[str, Any]], geometry: bool = False) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    integers = {"source_id", "area_count"}
    booleans = {"source_valid", "coverage_eligible", "presentation_valid"}
    schema = pa.schema(
        [
            (
                key,
                pa.binary()
                if key == "geometry"
                else pa.int64()
                if key in integers
                else pa.bool_()
                if key in booleans
                else pa.string(),
            )
            for key in rows[0]
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    metadata = {b"watergeo": encode({"product_version": PRODUCT_VERSION})}
    if geometry:
        metadata[b"geo"] = encode(
            {
                "version": "1.1.0",
                "primary_column": "geometry",
                "columns": {
                    "geometry": {
                        "encoding": "WKB",
                        "crs": CRS.from_epsg(27700).to_json_dict(),
                        "geometry_types": ["Polygon", "MultiPolygon"],
                    },
                },
            }
        )
    pq.write_table(table.replace_schema_metadata(metadata), path, compression="zstd")


def build_service_bundle(
    raw_root: Path,
    destination: Path,
    crosswalk_path: Path = Path(REVIEW),
    *,
    tippecanoe: str | None = None,
) -> dict[str, Any]:
    """Build locally and atomically; an existing edition can never be overwritten."""
    if destination.exists():
        raise ValueError("Bundle destination exists; choose a new immutable edition")
    crosswalk = read_crosswalk(crosswalk_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".services-") as temp:
        staging = Path(temp) / "bundle"
        staging.mkdir()
        manifest: dict[str, Any] = {
            "product_version": PRODUCT_VERSION,
            "datasets": {},
            "files": {},
            "source_crs": "EPSG:27700",
            "presentation_crs": "OGC:CRS84",
            "crosswalk_sha256": digest_file(crosswalk_path),
            "runtime": {
                "shapely": shapely.__version__,
                "geos": shapely.geos_version_string,
                "proj": __proj_version__,
            },
            "pcd_included": False,
        }
        companies: dict[str, dict[str, Any]] = {}
        services, areas, bridge, index = [], [], [], []
        for service in SERVICES:
            metadata, rows, features = decode_service(service, raw_root / service, crosswalk)
            manifest["datasets"][service] = metadata
            _write_table(staging / f"{service}.parquet", rows, geometry=True)
            (staging / f"{service}.geojson").write_bytes(
                encode(
                    {
                        "type": "FeatureCollection",
                        "features": features,
                        "geometry_role": "reprojected publisher source; not repaired",
                    }
                )
            )
            overview = []
            for feature in features:
                preview = shape(feature["geometry"]).simplify(0.001, preserve_topology=True)
                overview.append(
                    {
                        "type": "Feature",
                        "id": feature["id"],
                        "properties": {
                            key: feature["properties"][key]
                            for key in (
                                "boundary_id",
                                "company_id",
                                "service",
                                "source_id",
                                "source_valid",
                            )
                        },
                        "geometry": mapping(preview),
                    }
                )
            (staging / f"{service}-overview.geojson").write_bytes(
                encode(
                    {
                        "type": "FeatureCollection",
                        "features": overview,
                        "geometry_role": (
                            "display-only simplification; tolerance 0.001 degrees; no repair"
                        ),
                    }
                )
            )
            if tippecanoe:
                executable = shutil.which(tippecanoe)
                if executable is None:
                    raise ValueError("Tippecanoe executable not found")
                subprocess.run(  # noqa: S603
                    [
                        executable,
                        "--quiet",
                        "-Z0",
                        "-z8",
                        "--no-feature-limit",
                        "--no-tile-size-limit",
                        f"--layer={service.replace('-', '_')}",
                        f"--attribution={metadata['attribution']}",
                        f"--output={service}.pmtiles",
                        f"{service}-overview.geojson",
                    ],
                    cwd=staging,
                    check=True,
                    timeout=1800,
                )
                manifest.setdefault("tiles", {})[service] = {
                    "geometry_role": "overview only; simplified, clipped, quantized",
                    "source": f"{service}-overview.geojson",
                }
            services.append(
                {
                    "service": service,
                    "dataset": metadata["dataset"],
                    "snapshot_sha256": metadata["sha256"],
                    "release": metadata["release"],
                    "area_count": len(rows),
                    "attribution": metadata["attribution"],
                    "licence_name": metadata["licence_name"],
                    "licence_version": None,
                }
            )
            for row, feature in zip(rows, features, strict=True):
                area = {k: v for k, v in row.items() if k != "geometry"}
                areas.append(area)
                bridge.append(
                    {
                        "boundary_id": row["boundary_id"],
                        "company_id": row["company_id"],
                        "service": service,
                        "snapshot_sha256": row["snapshot_sha256"],
                        "review_reference": row["mapping_review"],
                    }
                )
                companies[row["company_id"]] = {
                    "company_id": row["company_id"],
                    "company_name": row["company_name"],
                    "identity_scope": "reviewed historical publisher grouping; not legal identity",
                }
                file = f"areas/{service}/{row['source_id']}.geojson"
                (staging / file).parent.mkdir(parents=True, exist_ok=True)
                (staging / file).write_bytes(encode(feature))
                index.append({**area, "geometry_file": file})
        for name, records in (
            ("companies", list(companies.values())),
            ("services", services),
            ("areas", areas),
            ("company-area-bridge", bridge),
        ):
            _write_table(staging / f"{name}.parquet", records)
        (staging / "index.json").write_bytes(encode({"areas": index, "services": services}))
        (staging / "company-crosswalk.json").write_bytes(crosswalk_path.read_bytes())
        for artifact in sorted(staging.rglob("*")):
            if artifact.is_file():
                manifest["files"][artifact.relative_to(staging).as_posix()] = {
                    "bytes": artifact.stat().st_size,
                    "sha256": digest_file(artifact),
                }
        manifest["validation_results"] = {
            "feature_count": len(areas),
            "bridge_count": len(bridge),
            "source_invalid_count": sum(not row["source_valid"] for row in areas),
            "round_trip": "exact source WKB and presentation WKB hashes after GeoJSON round trip",
            "coverage": "invalid source features quarantined; no overlap/gap or legal review",
        }
        payload = encode(manifest)
        (staging / "manifest.json").write_bytes(payload)
        (staging / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
        validate_service_bundle(staging)
        staging.rename(destination)
    return manifest


def validate_service_bundle(
    root: Path, expected_manifest_sha256: str | None = None
) -> dict[str, Any]:
    """Validate checksums, provenance, relations, and exact WKB/GeoJSON round trips."""
    import pyarrow.parquet as pq

    actual = digest_file(root / "manifest.json")
    expected = expected_manifest_sha256 or (root / "manifest.sha256").read_text().strip()
    if actual != expected:
        raise ValueError("Manifest checksum mismatch")
    manifest: dict[str, Any] = json.loads((root / "manifest.json").read_bytes())
    if manifest["product_version"] != PRODUCT_VERSION or manifest["pcd_included"] is not False:
        raise ValueError("Unsupported boundary product")
    expected_files = set(manifest["files"]) | {"manifest.json", "manifest.sha256"}
    actual_files = {
        file.relative_to(root).as_posix()
        for file in root.rglob("*")
        if file.is_file() or file.is_symlink()
    }
    if actual_files != expected_files:
        raise ValueError("Bundle contains missing or unlisted files")
    for name, evidence in manifest["files"].items():
        file = root / name
        if Path(name).is_absolute() or ".." in Path(name).parts or file.is_symlink():
            raise ValueError("Unsafe bundle path")
        if file.stat().st_size != evidence["bytes"] or digest_file(file) != evidence["sha256"]:
            raise ValueError(f"File checksum mismatch: {name}")
    identities: set[str] = set()
    for service, (source, contract) in SERVICES.items():
        dataset = manifest["datasets"][service]
        if dataset["sha256"] != source.expected_sha256 or dataset["licence_version"] is not None:
            raise ValueError("Source identity or licence metadata changed")
        table = pq.read_table(root / f"{service}.parquet")
        geo = json.loads(table.schema.metadata[b"geo"])
        if CRS.from_json_dict(geo["columns"]["geometry"]["crs"]).to_epsg() != 27700:
            raise ValueError("GeoParquet source CRS changed")
        rows = table.to_pylist()
        if len(rows) != contract.expected_record_count:
            raise ValueError("Source count mismatch")
        invalid = set()
        layer = json.loads((root / f"{service}.geojson").read_bytes())
        if len(layer["features"]) != len(rows):
            raise ValueError("GeoJSON inventory mismatch")
        for row, feature in zip(rows, layer["features"], strict=True):
            identity = boundary_id(source.dataset, source.expected_sha256, row["source_id"])
            if row["boundary_id"] != identity or identity in identities:
                raise ValueError("Composite identity collision")
            identities.add(identity)
            if hashlib.sha256(row["geometry"]).hexdigest() != row["source_wkb_sha256"]:
                raise ValueError("WKB round-trip mismatch")
            geometry = shapely.from_wkb(row["geometry"])
            projected = shape(feature["geometry"])
            projected_hash = hashlib.sha256(
                shapely.to_wkb(projected, byte_order=1, include_srid=False)
            ).hexdigest()
            if (
                feature["id"] != identity
                or feature["properties"] != {k: v for k, v in row.items() if k != "geometry"}
                or projected_hash != row["presentation_wkb_sha256"]
                or row["presentation_valid"] != bool(projected.is_valid)
            ):
                raise ValueError("GeoJSON geometry or provenance round-trip mismatch")
            individual = json.loads(
                (root / f"areas/{service}/{row['source_id']}.geojson").read_bytes()
            )
            if individual != feature:
                raise ValueError("Individual feature mismatch")
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("Unexpected geometry")
            if not geometry.is_valid:
                invalid.add(row["source_id"])
            if (
                row["coverage_eligible"] != bool(geometry.is_valid)
                or row["source_valid"] != bool(geometry.is_valid)
                or row["licence_statement"] != SOURCE_LICENCE_STATEMENT
            ):
                raise ValueError("Geometry eligibility or licence mismatch")
        if invalid != contract.expected_invalid_ids:
            raise ValueError("Invalid geometry set changed")
        if {r["source_id"] for r in rows} != contract.expected_ids:
            raise ValueError("Source ID inventory changed")
    areas = pq.read_table(root / "areas.parquet").to_pylist()
    bridge = pq.read_table(root / "company-area-bridge.parquet").to_pylist()
    company_rows = pq.read_table(root / "companies.parquet").to_pylist()
    companies = {r["company_id"] for r in company_rows}
    if len(companies) != len(company_rows):
        raise ValueError("Duplicate company dimensions")
    reviewed = read_crosswalk(root / "company-crosswalk.json")
    area_by_id = {r["boundary_id"]: r for r in areas}
    for row in bridge:
        area = area_by_id.get(row["boundary_id"])
        if area is None or area["company_id"] != row["company_id"]:
            raise ValueError("Bridge company mismatch")
        mapping_row = reviewed.get((area["dataset"], area["COMPANY"], area["Acronym"]))
        if mapping_row is None or mapping_row["company_id"] != row["company_id"]:
            raise ValueError("Missing reviewed company mapping")
    if (
        len(areas) != len(identities)
        or {r["boundary_id"] for r in areas} != identities
        or len(bridge) != len(identities)
        or {r["boundary_id"] for r in bridge} != identities
        or any(r["company_id"] not in companies or not r["review_reference"] for r in bridge)
    ):
        raise ValueError("Missing company-to-area mappings")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/ofwat"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, default=Path(REVIEW))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--tippecanoe", help="Optional overview PMTiles executable")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        manifest = validate_service_bundle(args.output)
    else:
        if args.fetch:
            for service, (source, _) in SERVICES.items():
                fetch_boundary_source(source, raw_root=args.raw_root / service)
        manifest = build_service_bundle(
            args.raw_root,
            args.output,
            args.crosswalk,
            tippecanoe=args.tippecanoe,
        )
    print(
        json.dumps(
            {
                "product_version": manifest["product_version"],
                "manifest_sha256": digest_file(args.output / "manifest.json"),
                "files": len(manifest["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()
