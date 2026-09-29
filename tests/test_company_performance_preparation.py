import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from watergeo.ingestion.phase15_client import read_bundle
from watergeo.ingestion.phase15_sources import EA_LICENCE, normalize_company_performance
from watergeo.operations.company_performance import (
    CompanyPerformancePreparationError,
    main,
    prepare,
)

HEADERS = [
    "Company ID",
    "Company name",
    "Period",
    "Measure code",
    "Measure name",
    "Value",
    "Unit",
    "Definition",
    "Definition source",
]


def xlsx_archive(
    path: Path,
    sheet_xml: str,
    sheet: str = "Reviewed data",
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


def xlsx(path: Path, rows: list[list[object]], sheet: str = "Reviewed data") -> None:
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
    sheet_xml = "".join(rendered_rows)
    xlsx_archive(path, sheet_xml, sheet)


def review(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "watergeo-company-performance-review-v1",
                "publisher": "Ofwat",
                "licence": EA_LICENCE,
                "publication": "Water Company Performance Report 2024-25",
                "sheet": "Reviewed data",
                "columns": dict(
                    zip(
                        (
                            "company_id",
                            "company_name",
                            "reporting_period",
                            "measure_code",
                            "measure_name",
                            "value",
                            "unit",
                            "definition",
                            "definition_source",
                        ),
                        HEADERS,
                        strict=True,
                    )
                ),
                "missing_values": ["", ".."],
                "not_applicable_values": ["N/A"],
                "boundary_crosswalk_version": "ofwat-to-water-supply-v1",
                "boundary_crosswalk": {"ANH": "AWS"},
            }
        )
    )


def test_prepares_loadable_evidence_and_preserves_value_states(tmp_path: Path) -> None:
    workbook = tmp_path / "official.xlsx"
    contract = tmp_path / "review.json"
    review(contract)
    xlsx(
        workbook,
        [
            HEADERS,
            [
                "ANH",
                "Anglian Water",
                "2024-25",
                "M1",
                "Measure 1",
                0,
                "count",
                "Definition",
                "Table 1",
            ],
            [
                "ANH",
                "Anglian Water",
                "2024-25",
                "M2",
                "Measure 2",
                "..",
                "%",
                "Definition",
                "Table 2",
            ],
            [
                "ANH",
                "Anglian Water",
                "2024-25",
                "M3",
                "Measure 3",
                "N/A",
                "count",
                "Definition",
                "Table 3",
            ],
        ],
    )
    directory, summary = prepare(workbook, contract, tmp_path / "evidence")
    manifest, product = read_bundle(
        directory,
        lambda values: normalize_company_performance(values["company-performance.json"]),
    )
    assert summary == {
        "companies": 1,
        "periods": 1,
        "measures": 3,
        "rows": 3,
        "missing": 1,
        "not_applicable": 1,
        "rejected": 0,
    }
    assert [row["value"] for row in product.secondary] == [0.0, None, None]
    assert product.entities[0]["boundary_company_acronym"] == "AWS"
    payload = json.loads((directory / "company-performance.json").read_text())
    assert (
        payload["preparation"]["workbook_sha256"]
        == hashlib.sha256(workbook.read_bytes()).hexdigest()
    )
    assert manifest["evidence_state"] == "validated"


def test_rejects_changed_sheet_columns_and_unreviewed_values(tmp_path: Path) -> None:
    contract = tmp_path / "review.json"
    review(contract)
    changed = tmp_path / "changed.xlsx"
    xlsx(changed, [[*HEADERS[:-1], "Changed source"], ["value"] * len(HEADERS)])
    with pytest.raises(CompanyPerformancePreparationError, match="columns changed"):
        prepare(changed, contract, tmp_path / "changed-output")
    bad_value = tmp_path / "bad-value.xlsx"
    xlsx(
        bad_value,
        [
            HEADERS,
            [
                "ANH",
                "Anglian Water",
                "2024-25",
                "M1",
                "Measure",
                "unknown",
                "count",
                "Definition",
                "Table",
            ],
        ],
    )
    with pytest.raises(CompanyPerformancePreparationError, match="numeric performance"):
        prepare(bad_value, contract, tmp_path / "bad-output")


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf"])
def test_cli_rejects_non_finite_performance_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], raw_value: str
) -> None:
    workbook = tmp_path / f"{raw_value}.xlsx"
    contract = tmp_path / "review.json"
    review(contract)
    xlsx(
        workbook,
        [
            HEADERS,
            [
                "ANH",
                "Anglian Water",
                "2024-25",
                "M1",
                "Measure",
                raw_value,
                "count",
                "Definition",
                "Table",
            ],
        ],
    )

    result = main(
        [
            str(workbook),
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
    contract = tmp_path / "review.json"
    review(contract)
    xlsx_archive(
        workbook,
        '<row r="1"><c r="A1" t="s"><v>-1</v></c></row>',
        shared_strings_xml=(
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>Company ID</t></si></sst>"
        ),
    )

    with pytest.raises(CompanyPerformancePreparationError, match="shared workbook string"):
        prepare(workbook, contract, tmp_path / "output")


def test_rejects_duplicate_cell_position(tmp_path: Path) -> None:
    workbook = tmp_path / "duplicate-cell.xlsx"
    contract = tmp_path / "review.json"
    review(contract)
    xlsx_archive(
        workbook,
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Company ID</t></is></c>'
        '<c r="A1" t="inlineStr"><is><t>Replacement</t></is></c></row>',
    )

    with pytest.raises(CompanyPerformancePreparationError, match="duplicate cell position"):
        prepare(workbook, contract, tmp_path / "output")
