from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook


SCRIPT = Path("scripts/prepare_ci_headless_fixture.py")


def test_prepare_ci_headless_fixture_script_exists() -> None:
    assert SCRIPT.exists(), "missing scripts/prepare_ci_headless_fixture.py"


def test_prepare_ci_headless_fixture_creates_anchors_and_workbooks(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "config" / "anchors").mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project_root),
            "--as-of",
            "2026-02-20",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr

    crm_anchor = project_root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    inbound_anchor = project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
    assert crm_anchor.is_symlink()
    assert inbound_anchor.is_symlink()
    assert crm_anchor.resolve(strict=True).exists()
    assert inbound_anchor.resolve(strict=True).exists()

    wb = load_workbook(crm_anchor.resolve(strict=True), read_only=True, data_only=True)
    try:
        assert "SALES_KSP_CRM_1" in wb.sheetnames
    finally:
        wb.close()
