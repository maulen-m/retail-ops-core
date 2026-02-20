from __future__ import annotations

import subprocess
import sys
import sqlite3
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


def test_prepare_ci_headless_fixture_creates_strict_gate_artifacts(tmp_path: Path) -> None:
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

    db_path = project_root / "db" / "app.db"
    assert db_path.exists(), "fixture must create db/app.db for strict validators"

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM sales_fact_v2").fetchone()[0]
    assert rows >= 14, "fixture should seed overlap rows for workbook anchor validation"

    dashboard_path = project_root / "exports" / "po_dashboard_data.json"
    assert dashboard_path.exists(), "fixture must create dashboard payload for strict validators"

    snapshot = project_root / "config" / "business_insides" / "BUSINESS_INSIDES_2026-02-20.md"
    assert snapshot.exists(), "fixture must create business-insides snapshot for strict validators"

    dim_sku_light = project_root / "config" / "anchors" / "fixtures" / "DIM_SKU_LIGHT_V5.fixture.xlsx"
    assert dim_sku_light.exists(), "fixture must create dim-sku-light workbook for alignment validator"
