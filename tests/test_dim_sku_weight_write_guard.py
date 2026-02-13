from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.migrate_025_dim_sku_weight_guard import (
    migrate,
    validate_dim_sku_weight_guard_schema,
)
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
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, active_flag)
        VALUES ('CL_OC_MEN_LINE52_BLACK', 'LINE52', 'CL', 47, 0.07, 1)
        """
    )
    conn.commit()
    conn.close()


def _write_dim_sku_light(path: Path) -> None:
    df = pd.DataFrame(
        [
            {"SKU_key": "CL_OC_MEN_LINE52_BLACK", "Type": "CL", "Wt (kg)": 0.95, "CNY": 47, "AvgPrc": 9392, "Active": 1},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DIM_SKU_light_v5", index=False, startrow=1)


def test_guard_schema_validation_fails_when_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    errors = validate_dim_sku_weight_guard_schema(db_path)
    assert errors


def test_weight_update_blocked_without_guard_after_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(
            "UPDATE dim_sku SET weight_kg = 0.95 WHERE sku_key = 'CL_OC_MEN_LINE52_BLACK'"
        )
    conn.close()


def test_non_weight_update_allowed_after_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE dim_sku SET base_cost_cny = 55 WHERE sku_key = 'CL_OC_MEN_LINE52_BLACK'"
    )
    conn.commit()
    updated = conn.execute(
        "SELECT base_cost_cny FROM dim_sku WHERE sku_key = 'CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()[0]
    conn.close()
    assert float(updated) == 55.0


def test_canonical_sync_updates_weight_with_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "dim_light.xlsx"
    _init_db(db_path)
    _write_dim_sku_light(xlsx_path)
    migrate(db_path)
    monkeypatch.setenv("ENABLE_DIM_SKU_SYNC_WRITE", "1")

    sync_dim_sku_from_dim_sku_light(
        xlsx_path=xlsx_path,
        db_path=db_path,
        apply=True,
    )

    conn = sqlite3.connect(str(db_path))
    weight = conn.execute(
        "SELECT weight_kg FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()[0]
    conn.close()
    assert float(weight) == 0.95
