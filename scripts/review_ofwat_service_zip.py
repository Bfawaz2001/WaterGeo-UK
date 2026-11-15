"""Audit a local service ZIP against its manifest and the exact public archives.

The output is non-bulk review evidence. No tenant access or dataset publication.
"""

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow.parquet as pq

from watergeo.service_boundaries import (
    REVIEW,
    SERVICES,
    decode_service,
    digest_file,
    read_crosswalk,
    validate_service_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True, dest="archive")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/ofwat"))
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ofwat-zip-review-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(args.archive) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise ValueError("Duplicate ZIP members")
            if sum(info.file_size for info in archive.infolist()) > 512 * 1024 * 1024:
                raise ValueError("Oversized ZIP")
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise ValueError("Unsafe ZIP member")
                destination = root / info.filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))  # read verifies CRC
        manifest = validate_service_bundle(root, args.manifest_sha256)
        crosswalk = read_crosswalk(Path(REVIEW))
        results: dict[str, Any] = {}
        for service in SERVICES:
            metadata, original, _ = decode_service(service, args.raw_root / service, crosswalk)
            exported = pq.read_table(root / f"{service}.parquet").to_pylist()
            if exported != original:
                raise ValueError("Export differs from original public publisher features")
            results[service] = {
                "source_sha256": metadata["sha256"],
                "count": len(exported),
                "quarantined_ids": sorted(
                    row["source_id"] for row in exported if not row["coverage_eligible"]
                ),
                "original_wkb_and_attributes": "exact match to verified public archive decode",
            }
        report = json.loads((root / "validation-report.json").read_bytes())
        result = {
            "review_date": "2026-11-15",
            "zip_bytes": args.archive.stat().st_size,
            "zip_sha256": digest_file(args.archive),
            "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
            "zip_member_count": len(names),
            "checksummed_payload_count": len(manifest["files"]),
            "services": results,
            "validation_results": report["results"],
            "dimension_counts": {
                name: pq.read_table(root / f"{name}.parquet").num_rows
                for name in ("companies", "services", "areas", "company-area-bridge")
            },
            "governance": {
                "input_scope": (
                    "two exact fingerprint-pinned public Parliament archives "
                    "and reviewed company labels"
                ),
                "unlisted_zip_files": False,
                "pcd_input": False,
                "fabric_tenant_access": False,
                "original_source_field_count": 17,
                "source_geometry_policy": (
                    "original publisher features; invalid features quarantined"
                ),
            },
            "limitations": [
                "No canonical sewerage repair approved",
                "No real Fabric execution",
                "Optional PMTiles not generated",
                "Dataset remains local and ignored by Git",
            ],
        }
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    "features": sum(r["count"] for r in results.values()),
                    "zip_sha256": result["zip_sha256"],
                }
            )
        )


if __name__ == "__main__":
    main()
