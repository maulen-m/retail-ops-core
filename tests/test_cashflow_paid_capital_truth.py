import sqlite3
from pathlib import Path

import yaml

from core.cashflow.paid_capital_truth import compute_paid_capital_truth


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock REAL,
            inbound_stock REAL
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
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
    conn.executemany(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock, inbound_stock)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("2026-02-07", "SKU_1", 10, 5),
            ("2026-02-07", "SKU_2", 2, 3),
        ],
    )
    conn.executemany(
        """
        INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("SKU_1", 100, 0, 0),
            ("SKU_2", 200, 0, 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO po_part (
            po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("PO-4.1", "PO-4.1", "RECEIVED", 1_920_750, 670_800, 1, 1, 0, 0),
            ("PO-5.1", "PO-5", "IN_TRANSIT", 2_516_280, 728_304.8, 0, 0, 2_516_280, 728_304.8),
            ("PO-5.2", "PO-5", "IN_TRANSIT", 9_305_790, 3_085_347.3, 0, 0, 9_305_790, 3_085_347.3),
        ],
    )
    conn.commit()
    conn.close()


def _write_bank_yaml(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-02-08 12:10:23 GMT+5",
                "stores": {
                    "ACMEWEAR": {"accounts": {"kaspi_gold": {"balance_kzt": 2_000_000}}},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_compute_paid_capital_truth_respects_paid_flags_and_to_pay(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank_path = tmp_path / "bank_accounts.yaml"
    _seed_db(db_path)
    _write_bank_yaml(bank_path)

    result = compute_paid_capital_truth(db_path=db_path, bank_accounts_path=bank_path)

    assert result["cash_actual_kzt"] == 2_000_000.0
    assert result["inventory_on_hand_paid_kzt"] == 1_400.0
    assert result["inventory_inbound_paid_kzt"] == 2_591_550.0
    assert result["inbound_unpaid_obligations_kzt"] == 15_635_722.1
    assert result["total_capital_paid_kzt"] == 4_592_950.0


def test_compute_paid_capital_truth_includes_partial_paid_portion_from_to_pay(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank_path = tmp_path / "bank_accounts.yaml"
    _seed_db(db_path)
    _write_bank_yaml(bank_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO po_part (
            po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt
        ) VALUES ('PO-6.0', 'PO-6', 'IN_TRANSIT', 1145040, 460442.8, 0, 0, 145040, 60442.8)
        """
    )
    conn.commit()
    conn.close()

    result = compute_paid_capital_truth(db_path=db_path, bank_accounts_path=bank_path)
    assert result["inventory_inbound_paid_kzt"] == 3_991_550.0
