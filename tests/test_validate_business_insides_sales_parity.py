from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.generate_business_insides import generate_business_insides
from scripts.validate_business_insides_sales_parity import (
    validate_business_insides_sales_parity,
)


def _init_db(db_path: Path, *, max_sale_date: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            cogs REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock REAL
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            status TEXT,
            base_cost_kzt REAL,
            est_delivery_kzt REAL,
            is_paid_base INTEGER,
            is_paid_dlv INTEGER,
            to_pay_base_kzt REAL,
            to_pay_dlv_kzt REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 0, 30, 1.0)"
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock) VALUES ('2026-02-07','SKU_A',10)"
    )
    conn.execute(
        "INSERT INTO po_part (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt) VALUES ('PO-1.1','PO-1','IN_TRANSIT',10000,2000,1,1,0,0)"
    )
    for idx, day in enumerate(("2026-02-02", "2026-02-04", "2026-02-06", "2026-02-08"), start=1):
        if day > max_sale_date:
            continue
        conn.execute(
            """
            INSERT INTO sales_fact_v2
            (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
            VALUES (?, ?, 'SKU_A', 'SKU_A', 1, 500, 1000, 'DELIVERED', 0)
            """,
            (f"ORD-{idx}", day),
        )
    conn.commit()
    conn.close()


def _write_bank(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-02-20 10:00:00 GMT+5",
                "stores": {"ACMEWEAR": {"accounts": {"kaspi_gold": {"balance_kzt": 1_000_000}}}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_business_insides_sales_parity_passes_on_fresh_window(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank_path = tmp_path / "bank_accounts.yaml"
    output_dir = tmp_path / "business_insides"
    _init_db(db_path, max_sale_date="2026-02-08")
    _write_bank(bank_path)
    generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank_path,
        as_of="2026-02-08",
        output_dir=output_dir,
    )

    report = validate_business_insides_sales_parity(
        db_path=db_path,
        output_dir=output_dir,
        as_of="2026-02-08",
        report_root=tmp_path / "reports",
        require_recent_sales=True,
        max_sales_truth_lag_days=7,
        strict=True,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_business_insides_sales_parity_fails_on_stale_truth(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank_path = tmp_path / "bank_accounts.yaml"
    output_dir = tmp_path / "business_insides"
    _init_db(db_path, max_sale_date="2026-02-08")
    _write_bank(bank_path)
    generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank_path,
        as_of="2026-02-20",
        output_dir=output_dir,
    )

    with pytest.raises(RuntimeError, match="business_insides sales parity validation failed"):
        validate_business_insides_sales_parity(
            db_path=db_path,
            output_dir=output_dir,
            as_of="2026-02-20",
            report_root=tmp_path / "reports",
            require_recent_sales=True,
            max_sales_truth_lag_days=7,
            strict=True,
        )
