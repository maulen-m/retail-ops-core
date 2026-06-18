import hashlib
import sqlite3
from pathlib import Path

import yaml

from core.cashflow.paid_capital_truth import compute_paid_capital_truth
from scripts.generate_business_insides import generate_business_insides


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(db_path: Path) -> None:
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
        CREATE TABLE fact_cashflow_daily (
            date TEXT PRIMARY KEY,
            sales_accrued_kzt REAL,
            cogs_kzt REAL,
            profit_accrual_kzt REAL,
            inventory_on_delivery_close REAL
        );
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            assigned_size TEXT,
            my_size TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            internal_status TEXT,
            returned_to_warehouse INTEGER,
            status_updated_at TEXT,
            planned_shipment_date TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("SKU_A", "A", "BLACK", "CL", 32, 0.95, 0),
            ("SKU_B", "B", "WHITE", "CL", 24, 0.65, 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-02-07", "SKU_A", 10),
            ("2026-02-07", "SKU_B", 5),
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
            ("PO-1.1", "PO-1", "IN_TRANSIT", 100000, 20000, 1, 1, 0, 0),
            ("PO-2.1", "PO-2", "IN_TRANSIT", 50000, 12000, 0, 0, 50000, 12000),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_cashflow_daily (date, sales_accrued_kzt, cogs_kzt, profit_accrual_kzt, inventory_on_delivery_close)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-02-06", 0, 999999, -999999, 3000),
            ("2026-02-07", 0, 999999, -999999, 3000),
        ],
    )
    rows = []
    for day, net_rev, qty in [
        ("2026-02-02", 10000, 4),
        ("2026-02-03", 12000, 3),
        ("2026-02-04", 11000, 2),
        ("2026-02-05", 9000, 1),
        ("2026-02-07", 15000, 5),
        ("2026-02-08", 8000, 2),
    ]:
        rows.append(("ORD-" + day, day, "SKU_A", "SKU_A_M", qty, None, net_rev, "DELIVERED", 0))
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _init_db_fact_sales_only(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL,
            profit_line REAL
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
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt) "
        "VALUES ('SKU_A', 'A', 'BLACK', 'CL', 28, 0.9, 0)"
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock) VALUES ('2026-02-07', 'SKU_A', 10)"
    )
    conn.execute(
        "INSERT INTO po_part (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt) "
        "VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 100000, 20000, 1, 1, 0, 0)"
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-FS-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 10000, 1800, 8200)
        """
    )
    conn.commit()
    conn.close()


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


def test_business_insides_uses_sales_fact_v2_not_cashflow_daily_sales_accrued(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )

    assert result["performance"]["avg_7d_net_rev_kzt"] > 0
    assert result["performance"]["avg_7d_cogs_kzt"] < 999999


def test_generate_business_insides_does_not_mutate_source_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)
    before = _sha256(db_path)

    generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )

    assert _sha256(db_path) == before
    with sqlite3.connect(str(db_path)) as conn:
        view_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='view'
              AND name IN ('view_sales_line_truth', 'view_sales_daily_truth')
            """
        ).fetchone()[0]
    assert view_count == 0


def test_business_insides_last_7_days_no_false_zero_on_dates_with_delivered_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    last7 = {r["date"]: r for r in result["last_7_days"]}
    assert last7["2026-02-05"]["net_rev_kzt"] > 0
    assert last7["2026-02-07"]["net_rev_kzt"] > 0
    assert last7["2026-02-05"]["units_shipped"] > 0
    assert last7["2026-02-07"]["units_shipped"] > 0


def test_business_insides_marks_missing_day_as_na_when_no_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    last7 = {r["date"]: r for r in result["last_7_days"]}
    assert last7["2026-02-06"]["net_rev_kzt"] is None
    assert last7["2026-02-06"]["profit_kzt"] is None
    assert last7["2026-02-06"]["units_shipped"] is None


def test_business_insides_capital_components_match_paid_capital_truth(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    expected = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
    )

    assert result["capital"]["cash_actual_kzt"] == expected["cash_actual_kzt"]
    assert result["capital"]["total_capital_paid_kzt"] == expected["total_capital_paid_kzt"]


def test_business_insides_includes_unpaid_inbound_obligations(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    assert result["capital"]["inbound_unpaid_obligations_kzt"] > 0


def test_business_insides_works_with_fact_sales_only_via_canonical_views(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db_fact_sales_only(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    assert result["performance"]["avg_7d_net_rev_kzt"] > 0
    assert result["performance"]["avg_7d_cogs_kzt"] > 0
    assert any(row["units_shipped"] for row in result["last_7_days"] if row["units_shipped"] is not None)


def test_business_insides_uses_completed_fact_orders_when_sales_tables_are_stale(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, sku_key, sku_id, assigned_size, my_size,
            quantity, unit_price_kzt, internal_status, returned_to_warehouse, status_updated_at, planned_shipment_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-API-1", "ACMEWEAR", "SKU_A", "SKU_A_M", "XL", "", 2, 5000, "COMPLETED", 0, None, "2026-02-25"),
            ("ORD-API-2", "ACMEWEAR", "SKU_A", "SKU_A_M", "L", "", 1, 7000, "READY", 0, "2026-02-25 11:00:00", "2026-02-25"),
        ],
    )
    conn.commit()
    conn.close()

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-26",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    last7 = {r["date"]: r for r in result["last_7_days"]}
    assert last7["2026-02-25"]["net_rev_kzt"] == 10000.0
    assert result["performance"]["latest_sale_date_available"] == "2026-02-25"


def test_business_insides_can_overlay_stale_days_from_archive_orders(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    archive_file = tmp_path / "ArchiveOrders.xlsx"
    import pandas as pd

    pd.DataFrame(
        [
            {
                "№ заказа": "835100001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "2",
                "Сумма": "10000",
                "Склад передачи КД": "30000001_PP1",
            },
            {
                "№ заказа": "835100002",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "7000",
                "Склад передачи КД": "30137883_PP1",
            },
        ]
    ).to_excel(archive_file, index=False)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-26",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[str(archive_file)],
    )
    last7 = {r["date"]: r for r in result["last_7_days"]}
    assert last7["2026-02-25"]["units_delivered"] == 3.0
    assert last7["2026-02-25"]["net_rev_kzt"] == 17000.0
    assert result["archive_orders"]["status"] == "available"
    assert result["archive_orders"]["row_count"] == 2


def test_archive_orders_fallback_keeps_multi_line_orders_and_dedupes_duplicate_lines(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    archive_a = tmp_path / "ArchiveOrders_a.xlsx"
    archive_b = tmp_path / "ArchiveOrders_b.xlsx"
    import pandas as pd

    rows = [
        {
            "№ заказа": "835200001",
            "Дата изменения статуса": "25.02.2026",
            "Статус": "Выдан",
            "Количество": "1",
            "Сумма": "1500",
            "Склад передачи КД": "30000001_PP1",
            "Артикул": "SKU-A",
            "Название товара в Kaspi Магазине": "Item A",
        },
        {
            "№ заказа": "835200001",
            "Дата изменения статуса": "25.02.2026",
            "Статус": "Выдан",
            "Количество": "2",
            "Сумма": "3500",
            "Склад передачи КД": "30000001_PP1",
            "Артикул": "SKU-B",
            "Название товара в Kaspi Магазине": "Item B",
        },
    ]
    pd.DataFrame(rows).to_excel(archive_a, index=False)
    # Duplicate first line across another file should not double count.
    pd.DataFrame([rows[0]]).to_excel(archive_b, index=False)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-26",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[str(archive_a), str(archive_b)],
    )

    last7 = {r["date"]: r for r in result["last_7_days"]}
    assert last7["2026-02-25"]["units_delivered"] == 3.0
    assert last7["2026-02-25"]["net_rev_kzt"] == 5000.0
    assert result["archive_orders"]["days"]["2026-02-25"]["orders"] == 1
    assert result["archive_orders"]["row_count"] == 2


def test_business_insides_markdown_includes_units_shipped_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    content = Path(result["latest_path"]).read_text(encoding="utf-8")
    assert "Units Delivered (COMPLETED)" in content


def test_business_insides_reports_stale_recent_window_with_observed_history(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _init_db(db_path)
    _write_bank_yaml(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-20",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    perf = result["performance"]
    assert perf["observed_days_last_7_calendar"] == 0
    assert perf["latest_sale_date_available"] == "2026-02-08"
    assert perf["sales_truth_freshness_days"] == 12

    content = Path(result["latest_path"]).read_text(encoding="utf-8")
    assert "## Sales Truth Freshness" in content
    assert "Sales truth is stale for recent 7-day calendar window." in content
    assert "## Latest Observed Sales Days (Truth)" in content
    assert "2026-02-08" in content
