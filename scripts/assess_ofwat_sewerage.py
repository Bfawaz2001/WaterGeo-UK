"""Reproduce diagnostic sewerage ID 11 evidence; never approve or apply a repair."""

import argparse
import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import pyproj
import shapefile
import shapely
from shapely.geometry import shape

from watergeo.ingestion.ofwat_boundaries import OFWAT_SEWERAGE_V1_5
from watergeo.ingestion.ofwat_boundary_repair_assessment import assess_invalid_geometry
from watergeo.ingestion.ofwat_boundary_validation import (
    OFWAT_SEWERAGE_V1_5_CONTRACT,
    validate_boundary_archive,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/ofwat/sewerage"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = OFWAT_SEWERAGE_V1_5
    archive = args.raw_root / f"{source.expected_sha256}.zip"
    report = validate_boundary_archive(archive, contract=OFWAT_SEWERAGE_V1_5_CONTRACT)
    with (
        zipfile.ZipFile(archive) as zipped,
        shapefile.Reader(
            **{
                ext: io.BytesIO(zipped.read(f"{source.expected_basename}.{ext}"))
                for ext in ("shp", "shx", "dbf")
            },
            encoding="utf-8",
        ) as reader,
    ):
        item = next(x for x in reader.iterShapeRecords() if x.record["ID"] == 11)
        evidence = asdict(assess_invalid_geometry(11, shape(item.shape.__geo_interface__)))
    result = {
        "status": "diagnostic_only_not_approved",
        "validation": report.to_dict(),
        "shapely": shapely.__version__,
        "geos": shapely.geos_version_string,
        "pyproj": pyproj.__version__,
        "feature": evidence,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
