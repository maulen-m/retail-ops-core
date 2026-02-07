from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import openpyxl
from openpyxl.worksheet.table import Table, TableStyleInfo

from scripts.validate_crm_workbook_integrity import validate_workbook_integrity


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _make_workbook_with_table(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws["A1"] = "id"
    ws["B1"] = "value"
    ws["A2"] = "1"
    ws["B2"] = "x"
    table = Table(displayName="tb_SalesRaw", ref="A1:B2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(path)


def test_validate_workbook_integrity_ok(tmp_path: Path):
    wb_path = tmp_path / "ok.xlsx"
    _make_workbook_with_table(wb_path)

    result = validate_workbook_integrity(wb_path)
    assert result.errors == []


def test_validate_workbook_integrity_detects_table_column_mismatch(tmp_path: Path):
    wb_path = tmp_path / "bad_table.xlsx"
    _make_workbook_with_table(wb_path)

    with zipfile.ZipFile(wb_path, "r") as zin:
        table_xml = ET.fromstring(zin.read("xl/tables/table1.xml"))
        table_cols = table_xml.find(f"{{{MAIN_NS}}}tableColumns")
        assert table_cols is not None
        table_cols.set("count", "3")
        modified = ET.tostring(table_xml, encoding="utf-8", xml_declaration=True)

        tmp = tmp_path / "bad_table_tmp.xlsx"
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/tables/table1.xml":
                    zout.writestr(item, modified)
                else:
                    zout.writestr(item, zin.read(item.filename))
    tmp.replace(wb_path)

    result = validate_workbook_integrity(wb_path)
    assert any("table column mismatch" in err for err in result.errors)


def test_validate_workbook_integrity_detects_missing_table_target(tmp_path: Path):
    wb_path = tmp_path / "missing_target.xlsx"
    _make_workbook_with_table(wb_path)

    with zipfile.ZipFile(wb_path, "r") as zin:
        tmp = tmp_path / "missing_target_tmp.xlsx"
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/tables/table1.xml":
                    continue
                zout.writestr(item, zin.read(item.filename))
    tmp.replace(wb_path)

    result = validate_workbook_integrity(wb_path)
    assert any("tablePart target missing" in err for err in result.errors)

