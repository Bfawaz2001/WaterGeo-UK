"""Produce reproducible, non-bulk evidence from one locally built service bundle."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from watergeo.service_boundaries import digest_file, validate_service_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = validate_service_bundle(args.bundle)
    rows = pq.read_table(args.bundle / "areas.parquet").to_pylist()
    services: dict[str, Any] = {}
    for service in ("water-supply", "sewerage"):
        areas = [row for row in rows if row["service"] == service]
        company_bytes: defaultdict[str, int] = defaultdict(int)
        company_counts: Counter[str] = Counter()
        for row in areas:
            name = f"areas/{service}/{row['source_id']}.geojson"
            company_bytes[row["company_id"]] += manifest["files"][name]["bytes"]
            company_counts[row["company_id"]] += 1
        services[service] = {
            "source_sha256": manifest["datasets"][service]["sha256"],
            "record_count": len(areas),
            "source_invalid_ids": [row["source_id"] for row in areas if not row["source_valid"]],
            "presentation_invalid_ids": manifest["datasets"][service]["presentation_invalid_ids"],
            "inset_count": sum(row["AreaType"] == "inset" for row in areas),
            "company_count": len(company_counts),
            "largest_company_payloads": [
                {
                    "company_id": company,
                    "features": company_counts[company],
                    "individual_geojson_total_bytes": size,
                    "exceeds_existing_8_mib_collection_limit": size > 8 * 1024 * 1024,
                }
                for company, size in sorted(company_bytes.items(), key=lambda item: -item[1])[:5]
            ],
            "geojson": manifest["files"][f"{service}.geojson"],
            "geoparquet": manifest["files"][f"{service}.parquet"],
        }
    result = {
        "product_version": manifest["product_version"],
        "manifest_sha256": digest_file(args.bundle / "manifest.json"),
        "crosswalk_sha256": manifest["crosswalk_sha256"],
        "runtime": manifest["runtime"],
        "feature_count": len(rows),
        "company_count": pq.read_table(args.bundle / "companies.parquet").num_rows,
        "bridge_count": pq.read_table(args.bundle / "company-area-bridge.parquet").num_rows,
        "file_count": len(manifest["files"]),
        "services": services,
        "checks": [
            "all payload bytes/checksums",
            "independent source fingerprints",
            "complete source IDs/counts",
            "explicit source CRS",
            "exact WKB hash round trips",
            "exact reprojected GeoJSON round trips",
            "individual feature equality",
            "invalid publisher features quarantined",
            "reviewed bridge completeness",
            "publisher licence statements and unknown edition preserved",
        ],
        "limits": [
            "No canonical sewerage repair approved",
            "No overlap/gap or legal review",
            "PMTiles optional and not generated in this evidence run",
            "No Fabric tenant accessed",
            "No PCD input",
        ],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
