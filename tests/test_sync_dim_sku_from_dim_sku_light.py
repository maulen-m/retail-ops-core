import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.sync_dim_sku_from_dim_sku_light import sync_dim_sku_from_dim_sku_light


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, active_flag)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        [
            ("CL_OC_MEN_LINE52_BLACK", "LINE52", "CL", 55.0, 0.07),
            ("CL_OC_MEN_LINE51_WHITE", "LINE51", "CL", 65.0, 0.12),
        ],
    )
    conn.commit()
    conn.close()


def _write_dim_sku_light(path: Path) -> None:
    df = pd.DataFrame(
        [
            {"SKU_key": "CL_OC_MEN_LINE52_BLACK", "Type": "CL", "Wt (kg)": 0.95, "CNY": 47, "AvgPrc": 9392, "Active": 1},
            {"SKU_key": "CL_OC_MEN_LINE51_WHITE", "Type": "CL", "Wt (kg)": 1.20, "CNY": 60, "AvgPrc": 12990, "Active": 1},
            {"SKU_key": "CL_OC_MEN_LINE51_WHITE", "Type": "CL", "Wt (kg)": 0.07, "CNY": 0.19, "AvgPrc": 0.2, "Active": 1},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DIM_SKU_light_v7", index=False, startrow=1)


def test_dry_run_no_db_write(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)

    result = sync_dim_sku_from_dim_sku_light(
        xlsx_path=xlsx_path,
        db_path=db_path,
        apply=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT weight_kg, base_cost_cny FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()
    conn.close()

    assert result["apply"] is False
    assert result["rows_updated"] == 0
    assert float(row[0]) == 0.07
    assert float(row[1]) == 55.0


def test_apply_requires_enable_dim_sku_sync_write_and_apply_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)
    monkeypatch.delenv("ENABLE_DIM_SKU_SYNC_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_DIM_SKU_SYNC_WRITE=1"):
        sync_dim_sku_from_dim_sku_light(
            xlsx_path=xlsx_path,
            db_path=db_path,
            apply=True,
        )


def test_weight_sync_updates_only_weight_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)
    monkeypatch.setenv("ENABLE_DIM_SKU_SYNC_WRITE", "1")

    sync_dim_sku_from_dim_sku_light(
        xlsx_path=xlsx_path,
        db_path=db_path,
        apply=True,
        update_base_cost=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT weight_kg, base_cost_cny FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()
    conn.close()

    assert float(row[0]) == 0.95
    assert float(row[1]) == 55.0


def test_cost_columns_reference_only_unless_update_costs_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)
    monkeypatch.setenv("ENABLE_DIM_SKU_SYNC_WRITE", "1")

    sync_dim_sku_from_dim_sku_light(
        xlsx_path=xlsx_path,
        db_path=db_path,
        apply=True,
        update_base_cost=True,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT weight_kg, base_cost_cny FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()
    conn.close()

    assert float(row[0]) == 0.95
    assert float(row[1]) == 47.0


def test_idempotent_second_apply_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)
    monkeypatch.setenv("ENABLE_DIM_SKU_SYNC_WRITE", "1")

    sync_dim_sku_from_dim_sku_light(xlsx_path=xlsx_path, db_path=db_path, apply=True)
    second = sync_dim_sku_from_dim_sku_light(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    assert second["rows_updated"] == 0
