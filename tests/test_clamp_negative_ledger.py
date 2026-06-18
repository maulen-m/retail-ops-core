from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/clamp_negative_ledger.py")


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_type TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            qty_change INTEGER,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT,
            created_by TEXT
        );
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size)
        VALUES ('SKU_TEST_M', 'SKU_TEST', 'M');
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, running_balance, reference_id, reference_type,
            input_source, created_by
        ) VALUES (
            '2026-05-30', 'SALE', 'SKU_TEST', 'SKU_TEST_M', 'M', 'UNIVERSAL',
            -3, -3, 'ORDER-1', 'SALE', 'TEST', 'test'
        );
        """
    )
    conn.commit()
    conn.close()


def test_clamp_negative_ledger_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--snapshot-date",
            "2026-05-31",
            "--db",
            str(db_path),
            "--apply",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ENABLE_NEGATIVE_LEDGER_CLAMP_WRITE=1" in (result.stderr + result.stdout)


def test_clamp_negative_ledger_apply_inserts_adjustment_when_env_set(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    env = os.environ.copy()
    env["ENABLE_NEGATIVE_LEDGER_CLAMP_WRITE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--snapshot-date",
            "2026-05-31",
            "--db",
            str(db_path),
            "--apply",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT event_date, event_type, qty_change, reference_id
        FROM stock_ledger
        WHERE reference_id='NEGATIVE_CLAMP_2026-05-31'
        """
    ).fetchone()
    conn.close()

    assert row == ("2026-05-30", "ADJUSTMENT", 3, "NEGATIVE_CLAMP_2026-05-31")
