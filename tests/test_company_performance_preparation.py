import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from watergeo.ingestion.phase15_client import read_bundle
from watergeo.ingestion.phase15_sources import EA_LICENCE, normalize_company_performance
from watergeo.operations.company_performance import (
    CompanyPerformancePreparationError,
    main,
    prepare,
)

HEADERS = [
    "COMPANY_NAME",
    "COMPANY_ABBREVIATION",
    "UNIQUE_ITEM_REFERENCE",
    "SHORT_DESCRIPTION",
    "RAG",
    "YEAR",
    "VALUE",
    "UNITS",
]
COLUMNS = {
    "company_id": "COMPANY_ABBREVIATION",
    "company_name": "COMPANY_NAME",
    "reporting_period": "YEAR",
    "measure_code": "UNIQUE_ITEM_REFERENCE",
    "measure_name": "SHORT_DESCRIPTION",
    "value": "VALUE",
    "unit": "UNITS",
    "definition": "SHORT_DESCRIPTION",
    "definition_source": "RAG",
}
EMPTY_REJECTIONS = {"company": 0, "empty_metadata": 0, "unit": 0, "value": 0}


def xlsx_archive(
    path: Path,
    sheet_xml: str,
    sheet: str = "in",
    shared_strings_xml: str | None = None,
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{sheet_xml}</sheetData></worksheet>",
        )
        if shared_strings_xml is not None:
            archive.writestr("xl/sharedStrings.xml", shared_strings_xml)


def xlsx(path: Path, rows: list[list[object]], sheet: str = "in") -> None:
    def cell(column: int, row: int, value: object) -> str:
        letters = ""
        current = column
        while current:
            current, remainder = divmod(current - 1, 26)
            letters = chr(65 + remainder) + letters
        reference = f"{letters}{row}"
        if isinstance(value, (int, float)):
            return f'<c r="{reference}"><v>{value}</v></c>'
        return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'

    rendered_rows = []
    for number, row in enumerate(rows, 1):
        cells = "".join(cell(column, number, value) for column, value in enumerate(row, 1))
        rendered_rows.append(f'<row r="{number}">{cells}</row>')
    xlsx_archive(path, "".join(rendered_rows), sheet)


def dictionary(path: Path) -> None:
    path.write_text("Field,Field Description\nCOMPANY_NAME,Water company and sub-region name\n")


def review(
    path: Path,
    workbook: Path,
    data_dictionary: Path,
    expected_summary: dict[str, Any],
    *,
    source_columns: list[str] = HEADERS,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "watergeo-company-performance-review-v2",
                "publisher": "Ofwat",
                "licence": EA_LICENCE,
                "publication": "Water Company Performance Report 2024-25",
                "sheet": "in",
                "workbook_sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
                "dictionary_sha256": hashlib.sha256(data_dictionary.read_bytes()).hexdigest(),
                "source_columns": source_columns,
                "columns": COLUMNS,
                "missing_values": ["", ".."],
                "not_applicable_values": ["N/A"],
                "rejected_values": ["-", "Yes", "No", "PR24", "See RAG Guidance"],
                "rejected_units": ["Text"],
                "rejected_company_ids": ["-"],
                "reject_if_empty": ["measure_name", "definition"],
                "expected_summary": expected_summary,
                "boundary_crosswalk_version": "ofwat-to-water-supply-v1",
                "boundary_crosswalk": {"ANH": "AWS"},
            }
        )
    )


def accepted_summary() -> dict[str, Any]:
    return {
        "companies": 1,
        "periods": 1,
        "measures": 3,
        "rows": 3,
        "reported": 1,
        "zero": 1,
        "missing": 1,
        "not_applicable": 1,
        "rejected": 0,
        "rejected_by_reason": EMPTY_REJECTIONS,
    }


def test_prepares_loadable_evidence_and_preserves_value_states(tmp_path: Path) -> None:
    workbook = tmp_path / "official.xlsx"
    data_dictionary = tmp_path / "dictionary.csv"
    contract = tmp_path / "review.json"
    xlsx(
        workbook,
        [
            HEADERS,
            [
                "Anglian Water",
                "ANH",
                "M" * 140,
                "Measure 1",
                "3A.1",
                "2024-25",
                0,
                "no.",
            ],
            ["Anglian Water", "ANH", "M2", "Measure 2", "3A.2", "2024-25", "..", "%"],
            ["Anglian Water", "ANH", "M3", "Measure 3", "3A.3", "2024-25", "N/A", "no."],
        ],
    )
    dictionary(data_dictionary)
    review(contract, workbook, data_dictionary, accepted_summary())

    directory, summary = prepare(workbook, data_dictionary, contract, tmp_path / "evidence")
    manifest, product = read_bundle(
        directory,
        lambda values: normalize_company_performance(values["company-performance.json"]),
    )

    assert summary == accepted_summary()
    assert {row["measure_name"]: row["value"] for row in product.secondary} == {
        "Measure 1": 0.0,
        "Measure 2": None,
        "Measure 3": None,
    }
    assert product.entities[0]["boundary_company_acronym"] == "AWS"
    payload = json.loads((directory / "company-performance.json").read_text())
    assert (
        payload["preparation"]["workbook_sha256"]
        == hashlib.sha256(workbook.read_bytes()).hexdigest()
    )
    assert (
        payload["preparation"]["dictionary_sha256"]
        == hashlib.sha256(data_dictionary.read_bytes()).hexdigest()
    )
    assert payload["preparation"]["summary"] == accepted_summary()
    assert manifest["evidence_state"] == "validated"


def test_explicitly_reports_reviewed_row_exclusions(tmp_path: Path) -> None:
    workbook = tmp_path / "official.xlsx"
    data_dictionary = tmp_path / "dictionary.csv"
    contract = tmp_path / "review.json"
    xlsx(
        workbook,
        [
            HEADERS,
            ["Anglian Water", "ANH", "M1", "Measure", "3A.1", "2024-25", 1, "no."],
            ["-", "-", "INDEX", "", "", "2024-25", 100, "no."],
            ["Anglian Water", "ANH", "M2", "Question", "3A.2", "2024-25", "Yes", "Text"],
            ["Anglian Water", "ANH", "M3", "", "3A.3", "2024-25", 2, "no."],
            ["Anglian Water", "ANH", "M4", "Forecast", "3A.4", "2024-25", "-", "£m"],
        ],
    )
    dictionary(data_dictionary)
    expected = {
        "companies": 1,
        "periods": 1,
        "measures": 1,
        "rows": 1,
        "reported": 1,
        "zero": 0,
        "missing": 0,
        "not_applicable": 0,
        "rejected": 4,
        "rejected_by_reason": {"company": 1, "empty_metadata": 1, "unit": 1, "value": 1},
    }
    review(contract, workbook, data_dictionary, expected)

    _, summary = prepare(workbook, data_dictionary, contract, tmp_path / "evidence")

    assert summary == expected


def test_rejects_changed_columns_unreviewed_values_and_source_hashes(tmp_path: Path) -> None:
    data_dictionary = tmp_path / "dictionary.csv"
    dictionary(data_dictionary)
    changed = tmp_path / "changed.xlsx"
    contract = tmp_path / "review.json"
    xlsx(changed, [[*HEADERS[:-1], "Changed unit"], ["value"] * len(HEADERS)])
    review(contract, changed, data_dictionary, accepted_summary())
    with pytest.raises(CompanyPerformancePreparationError, match="columns changed"):
        prepare(changed, data_dictionary, contract, tmp_path / "changed-output")

    bad_value = tmp_path / "bad-value.xlsx"
    xlsx(
        bad_value,
        [
            HEADERS,
            ["Anglian Water", "ANH", "M1", "Measure", "3A.1", "2024-25", "unknown", "no."],
        ],
    )
    review(contract, bad_value, data_dictionary, accepted_summary())
    with pytest.raises(CompanyPerformancePreparationError, match="numeric performance"):
        prepare(bad_value, data_dictionary, contract, tmp_path / "bad-output")

    data_dictionary.write_text("changed")
    with pytest.raises(CompanyPerformancePreparationError, match="checksum changed"):
        prepare(bad_value, data_dictionary, contract, tmp_path / "hash-output")


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf"])
def test_cli_rejects_non_finite_performance_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], raw_value: str
) -> None:
    workbook = tmp_path / f"{raw_value}.xlsx"
    data_dictionary = tmp_path / "dictionary.csv"
    contract = tmp_path / "review.json"
    xlsx(
        workbook,
        [
            HEADERS,
            ["Anglian Water", "ANH", "M1", "Measure", "3A.1", "2024-25", raw_value, "no."],
        ],
    )
    dictionary(data_dictionary)
    review(contract, workbook, data_dictionary, accepted_summary())

    result = main(
        [
            str(workbook),
            "--dictionary",
            str(data_dictionary),
            "--review",
            str(contract),
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    assert result == 1
    rejected = json.loads(capsys.readouterr().err)
    assert rejected["status"] == "rejected"
    assert rejected["rejected"] == 1
    assert "Invalid numeric performance value" in rejected["error"]


def test_rejects_negative_shared_string_index(tmp_path: Path) -> None:
    workbook = tmp_path / "negative-shared-string.xlsx"
    data_dictionary = tmp_path / "dictionary.csv"
    contract = tmp_path / "review.json"
    xlsx_archive(
        workbook,
        '<row r="1"><c r="A1" t="s"><v>-1</v></c></row>',
        shared_strings_xml=(
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>COMPANY_NAME</t></si></sst>"
        ),
    )
    dictionary(data_dictionary)
    review(contract, workbook, data_dictionary, accepted_summary())

    with pytest.raises(CompanyPerformancePreparationError, match="shared workbook string"):
        prepare(workbook, data_dictionary, contract, tmp_path / "output")


def test_rejects_duplicate_cell_position(tmp_path: Path) -> None:
    workbook = tmp_path / "duplicate-cell.xlsx"
    data_dictionary = tmp_path / "dictionary.csv"
    contract = tmp_path / "review.json"
    xlsx_archive(
        workbook,
        '<row r="1"><c r="A1" t="inlineStr"><is><t>COMPANY_NAME</t></is></c>'
        '<c r="A1" t="inlineStr"><is><t>Replacement</t></is></c></row>',
    )
    dictionary(data_dictionary)
    review(contract, workbook, data_dictionary, accepted_summary())

    with pytest.raises(CompanyPerformancePreparationError, match="duplicate cell position"):
        prepare(workbook, data_dictionary, contract, tmp_path / "output")
