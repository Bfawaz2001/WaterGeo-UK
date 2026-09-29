"""Prepare reviewed Ofwat workbook rows as loadable WaterGeo JSON evidence."""

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from watergeo.ingestion.phase15_client import create_bundle
from watergeo.ingestion.phase15_sources import (
    BOUNDARY_CROSSWALK_VERSION,
    EA_LICENCE,
    OFWAT_WCPR_URL,
    Phase15SourceError,
    encoded,
    normalize_company_performance,
)

REVIEW_VERSION = "watergeo-company-performance-review-v1"
MAX_WORKBOOK_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ROWS = 100_000
FIELDS = (
    "company_id",
    "company_name",
    "reporting_period",
    "measure_code",
    "measure_name",
    "value",
    "unit",
    "definition",
    "definition_source",
)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class CompanyPerformancePreparationError(ValueError):
    """The operator workbook did not match its reviewed contract."""


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise CompanyPerformancePreparationError("Review JSON must be one real file")
    body = path.read_bytes()
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CompanyPerformancePreparationError("Invalid review JSON") from error
    if not isinstance(value, dict):
        raise CompanyPerformancePreparationError("Review must be a JSON object")
    return value, body


def _review(value: dict[str, Any]) -> tuple[str, dict[str, str], set[str], set[str]]:
    columns = value.get("columns")
    crosswalk = value.get("boundary_crosswalk")
    if (
        value.get("version") != REVIEW_VERSION
        or value.get("publisher") != "Ofwat"
        or value.get("licence") != EA_LICENCE
        or value.get("boundary_crosswalk_version") != BOUNDARY_CROSSWALK_VERSION
        or not isinstance(value.get("publication"), str)
        or not value["publication"].strip()
        or not isinstance(value.get("sheet"), str)
        or not value["sheet"].strip()
        or not isinstance(columns, dict)
        or set(columns) != set(FIELDS)
        or not all(isinstance(columns[field], str) and columns[field] for field in FIELDS)
        or len(set(columns.values())) != len(FIELDS)
        or not isinstance(crosswalk, dict)
        or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in crosswalk.items()
        )
    ):
        raise CompanyPerformancePreparationError("Invalid reviewed workbook contract")

    def states(name: str) -> set[str]:
        raw = value.get(name)
        if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
            raise CompanyPerformancePreparationError("Invalid reviewed value-state vocabulary")
        return {item.strip().casefold() for item in raw}

    missing = states("missing_values")
    not_applicable = states("not_applicable_values")
    if missing & not_applicable:
        raise CompanyPerformancePreparationError("Value-state vocabularies overlap")
    return value["sheet"], columns, missing, not_applicable


def _text(node: ElementTree.Element) -> str:
    return "".join(part.text or "" for part in node.findall(".//m:t", NS))


def _workbook_rows(path: Path, sheet_name: str) -> list[list[str]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_WORKBOOK_BYTES:
        raise CompanyPerformancePreparationError("Workbook is missing or exceeds the size limit")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 1_000 or sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
                raise CompanyPerformancePreparationError("Workbook archive exceeds reviewed limits")
            if any(
                PurePosixPath(info.filename).is_absolute()
                or ".." in PurePosixPath(info.filename).parts
                for info in infos
            ):
                raise CompanyPerformancePreparationError("Workbook contains an unsafe archive path")
            workbook = SafeElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = SafeElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relationships.findall("r:Relationship", REL_NS)
            }
            matches = [
                sheet
                for sheet in workbook.findall("m:sheets/m:sheet", NS)
                if sheet.attrib.get("name") == sheet_name
            ]
            if len(matches) != 1:
                raise CompanyPerformancePreparationError(
                    "Reviewed workbook sheet is missing or duplicated"
                )
            relationship = matches[0].attrib.get(DOC_REL)
            target = targets.get(relationship or "")
            if not target:
                raise CompanyPerformancePreparationError(
                    "Reviewed workbook sheet relationship is invalid"
                )
            normalized_target = PurePosixPath(target.lstrip("/"))
            if ".." in normalized_target.parts:
                raise CompanyPerformancePreparationError(
                    "Reviewed workbook sheet relationship is unsafe"
                )
            sheet_path = (
                normalized_target
                if normalized_target.parts[:1] == ("xl",)
                else PurePosixPath("xl") / normalized_target
            )
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = SafeElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [_text(item) for item in strings.findall("m:si", NS)]
            sheet = SafeElementTree.fromstring(archive.read(str(sheet_path)))
    except CompanyPerformancePreparationError:
        raise
    except (
        OSError,
        KeyError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
        DefusedXmlException,
    ) as error:
        raise CompanyPerformancePreparationError("Invalid XLSX workbook") from error

    rows: list[list[str]] = []
    for row in sheet.findall("m:sheetData/m:row", NS):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            if cell.find("m:f", NS) is not None:
                raise CompanyPerformancePreparationError("Workbook formulas are not accepted")
            reference = cell.attrib.get("r", "")
            match = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
            if match is None:
                raise CompanyPerformancePreparationError("Invalid workbook cell reference")
            column = 0
            for character in match.group(1):
                column = column * 26 + ord(character) - 64
            if column in values:
                raise CompanyPerformancePreparationError(
                    "Workbook row contains a duplicate cell position"
                )
            kind = cell.attrib.get("t")
            value_node = cell.find("m:v", NS)
            if kind == "inlineStr":
                value = _text(cell)
            elif value_node is None:
                value = ""
            elif kind == "s":
                try:
                    index = int(value_node.text or "")
                    if index < 0:
                        raise IndexError
                    value = shared[index]
                except (ValueError, IndexError) as error:
                    raise CompanyPerformancePreparationError(
                        "Invalid shared workbook string"
                    ) from error
            else:
                value = value_node.text or ""
            values[column] = value.strip()
        width = max(values, default=0)
        rows.append([values.get(index, "") for index in range(1, width + 1)])
        if len(rows) > MAX_ROWS:
            raise CompanyPerformancePreparationError("Workbook row limit exceeded")
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def prepare(workbook: Path, review_path: Path, output_root: Path) -> tuple[Path, dict[str, int]]:
    review, review_body = _read_json(review_path)
    sheet, columns, missing, not_applicable = _review(review)
    rows = _workbook_rows(workbook, sheet)
    expected = [columns[field] for field in FIELDS]
    if not rows or rows[0] != expected:
        raise CompanyPerformancePreparationError("Workbook columns changed from reviewed contract")
    items: list[dict[str, Any]] = []
    missing_count = 0
    not_applicable_count = 0
    companies: set[str] = set()
    periods: set[str] = set()
    measures: set[str] = set()
    company_names: dict[str, str] = {}
    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(expected) or not any(row):
            raise CompanyPerformancePreparationError(f"Invalid workbook row {row_number}")
        source = dict(zip(FIELDS, row, strict=True))
        raw_value = source.pop("value")
        if any(not source[field] for field in source):
            raise CompanyPerformancePreparationError(
                f"Required performance metadata is empty at row {row_number}"
            )
        previous_name = company_names.setdefault(source["company_id"], source["company_name"])
        if previous_name != source["company_name"]:
            raise CompanyPerformancePreparationError(
                f"Company identity changed name at row {row_number}"
            )
        state_key = raw_value.strip().casefold()
        if state_key in missing:
            value: float | None = None
            state = "missing"
            missing_count += 1
        elif state_key in not_applicable:
            value = None
            state = "not_applicable"
            not_applicable_count += 1
        else:
            try:
                value = float(raw_value)
            except ValueError as error:
                raise CompanyPerformancePreparationError(
                    f"Invalid numeric performance value at row {row_number}"
                ) from error
            if not math.isfinite(value):
                raise CompanyPerformancePreparationError(
                    f"Invalid numeric performance value at row {row_number}"
                )
            state = "reported"
        item = {**source, "value": value, "value_state": state}
        items.append(item)
        companies.add(source["company_id"])
        periods.add(source["reporting_period"])
        measures.add(source["measure_code"])
    if not items:
        raise CompanyPerformancePreparationError("Workbook contains no performance rows")
    workbook_body = workbook.read_bytes()
    payload = {
        "publisher": "Ofwat",
        "licence": EA_LICENCE,
        "publication": review["publication"],
        "boundary_crosswalk_version": BOUNDARY_CROSSWALK_VERSION,
        "boundary_crosswalk": review["boundary_crosswalk"],
        "preparation": {
            "version": REVIEW_VERSION,
            "workbook_sha256": hashlib.sha256(workbook_body).hexdigest(),
            "review_sha256": hashlib.sha256(review_body).hexdigest(),
            "sheet": sheet,
        },
        "items": items,
    }
    try:
        directory = create_bundle(
            "company-performance",
            {
                "company-performance.json": (
                    f"{OFWAT_WCPR_URL}#sha256={payload['preparation']['workbook_sha256']}",
                    encoded(payload),
                    {"content-type": "application/json"},
                )
            },
            lambda values: normalize_company_performance(values["company-performance.json"]),
            root=output_root,
        )
    except Phase15SourceError as error:
        raise CompanyPerformancePreparationError(str(error)) from error
    summary = {
        "companies": len(companies),
        "periods": len(periods),
        "measures": len(measures),
        "rows": len(items),
        "missing": missing_count,
        "not_applicable": not_applicable_count,
        "rejected": 0,
    }
    return directory, summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        directory, summary = prepare(arguments.workbook, arguments.review, arguments.output_root)
    except CompanyPerformancePreparationError as error:
        print(
            json.dumps({"status": "rejected", "rejected": 1, "error": str(error)}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"evidence_directory": str(directory), **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
