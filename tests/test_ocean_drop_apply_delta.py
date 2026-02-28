from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts.build_ocean_drop_reference_snapshot import (
    SnapshotError,
    _apply_to_sales_fact_v2,
    _build_apply_plan,
)


def _seed_sales_fact_v2(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT DEFAULT 'DELIVERED',
            return_flag INTEGER DEFAULT 0,
            return_date DATE,
            ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            source_file TEXT,
            api_updated_at DATETIME,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
            status, return_flag, return_date, source_file, api_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "ORD-KEEP",
                "2026-02-25",
                "SKU_KEEP",
                "SKU_KEEP_L",
                "L",
                "Offer Keep",
                "UNIVERSAL",
                1,
                500,
                0,
                None,
                500,
                None,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
            (
                "ORD-UPDATE",
                "2026-02-25",
                "SKU_A",
                "SKU_A_L",
                "L",
                "Offer A",
                "ACMEWEAR",
                1,
                100,
                0,
                None,
                100,
                None,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _snapshot_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order_id": "ORD-UPDATE",
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "sku_key": "SKU_A",
                "sku_id": "SKU_A_L",
                "my_size": "L",
                "offer_name": "Offer A",
                "status_internal": "DELIVERED",
                "return_flag": 0,
                "quantity": 2,
                "gross_rev_kzt": 200,
                "net_delivery_fee_kzt": 0,
            },
            {
                "order_id": "ORD-INSERT",
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "sku_key": "SKU_B",
                "sku_id": "SKU_B_M",
                "my_size": "M",
                "offer_name": "Offer B",
                "status_internal": "DELIVERED",
                "return_flag": 0,
                "quantity": 1,
                "gross_rev_kzt": 700,
                "net_delivery_fee_kzt": 0,
            },
        ]
    )


def test_build_apply_plan_delta_has_no_deletes(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_sales_fact_v2(db)
    conn = sqlite3.connect(db)
    try:
        plan = _build_apply_plan(
            conn=conn,
            snapshot_df=_snapshot_df(),
            as_of=date(2026, 2, 26),
            mode="delta",
        )
    finally:
        conn.close()

    assert plan["mode"] == "delta"
    assert plan["insert_count"] == 1
    assert plan["update_count"] == 1
    assert plan["delete_count"] == 0


def test_apply_replace_requires_second_delete_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    _seed_sales_fact_v2(db)
    conn = sqlite3.connect(db)
    try:
        plan = _build_apply_plan(
            conn=conn,
            snapshot_df=_snapshot_df(),
            as_of=date(2026, 2, 26),
            mode="replace",
        )
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_OCEAN_DROP_APPLY", "1")
    monkeypatch.delenv("ENABLE_OCEAN_DROP_DELETE", raising=False)

    with pytest.raises(SnapshotError, match="ENABLE_OCEAN_DROP_DELETE"):
        _apply_to_sales_fact_v2(
            db_path=db,
            as_of=date(2026, 2, 26),
            apply_plan=plan,
            backup_root=tmp_path / "backups",
        )


def test_apply_delta_updates_and_preserves_unrelated_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    _seed_sales_fact_v2(db)
    conn = sqlite3.connect(db)
    try:
        plan = _build_apply_plan(
            conn=conn,
            snapshot_df=_snapshot_df(),
            as_of=date(2026, 2, 26),
            mode="delta",
        )
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_OCEAN_DROP_APPLY", "1")

    result = _apply_to_sales_fact_v2(
        db_path=db,
        as_of=date(2026, 2, 26),
        apply_plan=plan,
        backup_root=tmp_path / "backups",
    )

    assert result["mode"] == "delta"
    assert result["rows_deleted"] == 0
    assert Path(result["backup_path"]).exists()

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            """
            SELECT order_id, quantity, net_rev
            FROM sales_fact_v2
            WHERE store_code='ACMEWEAR'
            ORDER BY order_id
            """
        ).fetchall()
        keep = conn.execute(
            "SELECT COUNT(*) FROM sales_fact_v2 WHERE order_id='ORD-KEEP'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert rows == [("ORD-INSERT", 1, 700.0), ("ORD-UPDATE", 2, 200.0)]
    assert keep == 1
