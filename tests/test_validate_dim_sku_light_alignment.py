import sqlite3
from pathlib import Path

import pandas as pd

from scripts.validate_dim_sku_light_alignment import validate_dim_sku_light_alignment


def _init_db(db_path: Path, *, print_weight: float, print_base: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            active_flag INTEGER DEFAULT 1
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, active_flag)
        VALUES (?, ?, ?, 1)
        """,
        [
            ("CL_OC_MEN_LINE52_BLACK", print_base, print_weight),
            ("CL_OC_MEN_LINE51_WHITE", 62.0, 1.2),
        ],
    )
    conn.commit()
    conn.close()


def _write_dim_light(path: Path) -> None:
    df = pd.DataFrame(
        [
            {"SKU_key": "CL_OC_MEN_LINE52_BLACK", "Type": "CL", "Wt (kg)": 0.95, "CNY": 47, "AvgPrc": 9392, "Active": 1},
            {"SKU_key": "CL_OC_MEN_LINE51_WHITE", "Type": "CL", "Wt (kg)": 1.20, "CNY": 62, "AvgPrc": 12990, "Active": 1},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DIM_SKU_light_v7", index=False)


def test_alignment_fails_when_weight_mismatch_exceeds_tolerance(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path, print_weight=0.07, print_base=47.0)
    _write_dim_light(xlsx_path)

    report = validate_dim_sku_light_alignment(
        db_path=db_path,
        workbook_path=xlsx_path,
        sheet_name="DIM_SKU_light_v7",
        weight_tol_kg=0.01,
    )

    assert report["ok"] is False
    assert report["weight_mismatch_count"] == 1
    assert report["error_count"] >= 1


def test_alignment_warns_not_fails_for_cost_reference_drift(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path, print_weight=0.95, print_base=70.0)
    _write_dim_light(xlsx_path)

    report = validate_dim_sku_light_alignment(
        db_path=db_path,
        workbook_path=xlsx_path,
        sheet_name="DIM_SKU_light_v7",
        weight_tol_kg=0.01,
        base_tol_cny=0.01,
    )

    assert report["ok"] is True
    assert report["weight_mismatch_count"] == 0
    assert report["base_mismatch_count"] == 1
    assert report["warning_count"] >= 1
