from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from scripts.generate_business_insides import generate_business_insides


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
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
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
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
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            quantity REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES ('ORD-1', '2026-02-26', 'SKU_A', 'SKU_A_L', 2, 1000, 2000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', 'A', 'BLACK', 'CL', 30, 1.0, 0)
        """
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock) VALUES ('2026-02-26', 'SKU_A', 10)"
    )
    conn.execute(
        """
        INSERT INTO po_part
        (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt)
        VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 10000, 2000, 1, 1, 0, 0)
        """
    )
    conn.execute("INSERT INTO fact_orders_kaspi (order_id, quantity) VALUES ('835039770', 1)")
    conn.commit()
    conn.close()


def _write_bank(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-02-26 10:00:00 GMT+5",
                "stores": {"ACMEWEAR": {"accounts": {"kaspi_gold": {"balance_kzt": 1000000}}}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_business_insides_separates_delivered_and_waybill_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _init_db(db_path)
    bank_path = tmp_path / "config" / "bank_accounts.yaml"
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    _write_bank(bank_path)

    selection_cache = tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
    _write_json(
        selection_cache,
        {
            "target_date": "2026-02-26",
            "include_overdue": True,
            "all_dates": False,
            "stores": {"ACMEWEAR": ["835039770"]},
        },
    )

    output_dir = tmp_path / "config" / "business_insides"
    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank_path,
        as_of="2026-02-26",
        output_dir=output_dir,
        waybill_selection_cache_path=selection_cache,
        archive_orders_globs=[],
    )
    content = Path(result["latest_path"]).read_text(encoding="utf-8")
    assert "Units Delivered (COMPLETED)" in content
    assert "## Waybill-State Shipment Snapshot" in content
    assert "Orders Shipped (Waybill Selection)" in content

    payload = json.loads(Path(result["latest_json_path"]).read_text(encoding="utf-8"))
    assert payload["last_7_days"][-1]["units_delivered"] == 2.0
    assert payload["waybill_snapshot"]["stores"]["ACMEWEAR"]["orders"] == 1
