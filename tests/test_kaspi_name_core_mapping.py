from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts import patch_kaspi_parsed_fields as patch_mod
from scripts import validate_kaspi_parsing_integrity as validate_mod


def _write_workbook(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "Артикул": "OF_SUIT-61_BLK_XL_48",
                "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL_48",
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "Kaspi_name_core": "WRONG_CORE",
                "Product_Type": "CL",
            }
        ]
    )
    df.to_excel(path, index=False)


def test_validate_kaspi_parsing_integrity_reports_line61_core_mismatch(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)

    report = validate_mod.validate_workbook(
        workbook=workbook,
        sheet_name="Sheet1",
        strict=False,
    )

    assert report["rows_scanned"] == 1
    assert report["anomaly_counts"]["line61_core_mismatch"] == 1
    assert report["hard_fail"] is True


def test_patch_kaspi_parsed_fields_defaults_to_dry_run(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    report = tmp_path / "report.csv"
    backup_dir = tmp_path / "backups"

    stats = patch_mod.run_patch(
        workbook=workbook,
        sheet_name="Sheet1",
        report=report,
        backup_dir=backup_dir,
        only_line61=True,
        apply=False,
    )

    assert stats["mode"] == "DRY_RUN"
    assert stats["rows_updated"] == 1
    assert report.exists()
    assert not backup_dir.exists()


def test_patch_kaspi_parsed_fields_blocks_apply_without_env_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    report = tmp_path / "report.csv"
    monkeypatch.delenv("ENABLE_KASPI_PARSING_PATCH_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_KASPI_PARSING_PATCH_WRITE=1"):
        patch_mod.run_patch(
            workbook=workbook,
            sheet_name="Sheet1",
            report=report,
            backup_dir=tmp_path / "backups",
            only_line61=True,
            apply=True,
        )
