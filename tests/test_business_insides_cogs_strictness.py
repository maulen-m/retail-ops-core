import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.generate_business_insides import generate_business_insides


def _write_bank_yaml(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-02-08 10:00:00 GMT+5",
                "stores": {
                    "ACMEWEAR": {
                        "accounts": {
                            "kaspi_gold": {"balance_kzt": 2_000_000},
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _seed_db(db_path: Path) -> None:
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
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
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
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'LINE61', 'BLACK', 'CL', 100, 1.5, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_UNRESOLVED', 'BAD', 'BLACK', 'CL', 70, NULL, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES ('ACMEWEAR', 'OF_SUIT-61_BLK_XL_50', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL', 1)
        """
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock) VALUES ('2026-02-07', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 10)"
    )
    conn.execute(
        "INSERT INTO po_part (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt) VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 100000, 20000, 1, 1, 0, 0)"
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-1", "2026-02-08", "OF_SUIT-61_BLK_XL_50", "OF_SUIT-61_BLK_XL_50_XL", 2, 0, 25000, "DELIVERED", 0),
            ("ORD-2", "2026-02-08", "SKU_UNRESOLVED", "SKU_UNRESOLVED_L", 1, 0, 6000, "DELIVERED", 0),
        ],
    )
    conn.commit()
    conn.close()


def test_business_insides_fails_when_unresolved_cogs_present(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    bank = tmp_path / "bank.yaml"
    _write_bank_yaml(bank)

    with pytest.raises(RuntimeError, match="Unresolved COGS rows"):
        generate_business_insides(
            db_path=db_path,
            bank_accounts_path=bank,
            as_of="2026-02-08",
            output_dir=tmp_path / "out",
            strict_cogs=True,
            archive_orders_globs=[],
        )


def test_business_insides_reports_unresolved_rows_and_sku_count(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    bank = tmp_path / "bank.yaml"
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "out",
        strict_cogs=False,
        archive_orders_globs=[],
    )

    assert result["unresolved_rows"] == 1
    assert result["unresolved_sku_count"] == 1


def test_business_insides_uses_formula_cogs_series(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    bank = tmp_path / "bank.yaml"
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "out",
        strict_cogs=False,
        archive_orders_globs=[],
    )
    day = {r["date"]: r for r in result["last_7_days"]}["2026-02-08"]

    # suit line formula cogs: 2 * (100*73 + 1.5*520*2.66) = 18749.6
    assert day["cogs_kzt"] == 18749.6


def test_business_insides_formula_cogs_is_not_base_only(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    bank = tmp_path / "bank.yaml"
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "out",
        strict_cogs=False,
        archive_orders_globs=[],
    )
    day = {r["date"]: r for r in result["last_7_days"]}["2026-02-08"]

    base_only = 2 * 100 * 75
    assert day["cogs_kzt"] > base_only
