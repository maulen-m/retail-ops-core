from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.worksheet.table import Table, TableStyleInfo

from scripts.backfill_line61_kaspi_core import (
    CANONICAL_LINE61_CORE,
    backfill_line61_kaspi_core,
)


def _build_fixture_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Kaspi_name_core", "SKU_key", "SKU_ID_KSP"]
    ws.append(headers)
    ws.append(["08.02.2026", "Спортивный_костюм_ACMEWEAR", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "OF_SUIT-61_BLK_XL"])
    ws.append(["08.02.2026", "Line51", "", "OF_SUIT-61_BLK_3XL"])
    ws.append(["08.02.2026", "Line51", "CL_OC_MEN_LINE52_BLACK", "OF_PRINT-51_BLK_L"])
    table = Table(displayName="tb_SalesRaw", ref="A1:D4")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(path)
    wb.close()


def test_backfill_line61_kaspi_core_dry_run_reports_without_writing(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    _build_fixture_workbook(workbook)

    stats = backfill_line61_kaspi_core(
        workbook=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        apply=False,
        backup_dir=tmp_path / "backups",
    )
    assert stats.line61_rows == 2
    assert stats.updated_rows == 2

    wb = openpyxl.load_workbook(workbook, data_only=True)
    ws = wb["SALES_KSP_CRM_1"]
    assert ws.cell(2, 2).value == "Спортивный_костюм_ACMEWEAR"
    assert ws.cell(3, 2).value == "Line51"
    wb.close()


def test_backfill_line61_kaspi_core_apply_updates_and_creates_backup(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    backup_dir = tmp_path / "backups"
    _build_fixture_workbook(workbook)

    stats = backfill_line61_kaspi_core(
        workbook=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        apply=True,
        backup_dir=backup_dir,
    )
    assert stats.line61_rows == 2
    assert stats.updated_rows == 2
    assert stats.backup_path is not None
    assert stats.backup_path.exists()
    assert stats.backup_path.parent == backup_dir

    wb = openpyxl.load_workbook(workbook, data_only=True)
    ws = wb["SALES_KSP_CRM_1"]
    assert ws.cell(2, 2).value == CANONICAL_LINE61_CORE
    assert ws.cell(3, 2).value == CANONICAL_LINE61_CORE
    assert ws.cell(4, 2).value == "Line51"
    wb.close()
