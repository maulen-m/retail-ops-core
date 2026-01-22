from __future__ import annotations

import sqlite3
import subprocess
from datetime import date
from pathlib import Path

from core.config.business_params import get_demand_overrides, set_demand_override


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    return db_path


def test_demand_override_active_window(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)

    set_demand_override(
        sku_key="TEST_SKU",
        d_override=42.0,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
        db_path=db_path,
    )

    active = get_demand_overrides(
        as_of_date=date(2026, 2, 1),
        db_path=db_path,
    )
    assert active.get("TEST_SKU") == 42.0

    inactive = get_demand_overrides(
        as_of_date=date(2026, 3, 2),
        db_path=db_path,
    )
    assert "TEST_SKU" not in inactive

    boundary = get_demand_overrides(
        as_of_date=date(2026, 3, 1),
        db_path=db_path,
    )
    assert "TEST_SKU" not in boundary


def test_upsert_demand_overrides_idempotent(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    script = Path(__file__).resolve().parent.parent / "scripts" / "upsert_demand_overrides.py"

    result1 = subprocess.run(
        ["python3", str(script), "--db", str(db_path), "--seed-defaults"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result1.returncode == 0

    result2 = subprocess.run(
        ["python3", str(script), "--db", str(db_path), "--seed-defaults"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result2.returncode == 0

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT sku_key, d_override, start_date, end_date FROM dim_demand_overrides"
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 5
    sku_keys = [row[0] for row in rows]
    assert sku_keys.count("CL_OC_MEN_LINE52_BLACK") == 2
    assert sku_keys.count("CL_OC_MEN_LINE51_WHITE") == 1
    assert sku_keys.count("CL_NEW-CLO2_MEN_SUIT-61_BLACK") == 1
    assert sku_keys.count("CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE") == 1
