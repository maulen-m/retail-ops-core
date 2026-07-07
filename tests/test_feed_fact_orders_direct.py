from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

from scripts.feed_fact_orders_kaspi_to_sales_fact_v2 import build_shadow_rows


def _init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL
        );
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT,
            quantity INTEGER,
            sell_price_kzt REAL,
            delivery_fee REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            unit_price_kzt REAL,
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            courier_transmission_date TEXT,
            status_updated_at TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            internal_status TEXT,
            source TEXT,
            source_file TEXT,
            imported_at TEXT,
            updated_at TEXT,
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT,
            delivery_cost_for_seller REAL,
            delivery_cost REAL,
            returned_to_warehouse INTEGER,
            kaspi_article TEXT,
            line_identity_key TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO dim_sku VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("CL_LINE52_BLACK", "Line52", "CL", 1, 0.5, 1000),
            ("CL_LINE51_WHITE", "Line51", "CL", 1, 0.6, 1200),
        ],
    )
    conn.executemany(
        "INSERT INTO dim_sku_size VALUES (?, ?, ?)",
        [
            ("CL_LINE52_BLACK_M", "CL_LINE52_BLACK", "M"),
            ("CL_LINE52_BLACK_XL", "CL_LINE52_BLACK", "XL"),
            ("CL_LINE51_WHITE_S", "CL_LINE51_WHITE", "S"),
        ],
    )
    conn.commit()
    return conn


def _insert_order(conn: sqlite3.Connection, **overrides) -> None:
    row = {
        "order_id": "ORD-1",
        "store_code": "ACMEWEAR",
        "kaspi_offer_name": "Offer Print",
        "sku_key": "CL_LINE52_BLACK",
        "sku_id": "CL_LINE52_BLACK_M",
        "my_size": "M",
        "quantity": 1,
        "unit_price_kzt": 10000,
        "created_at": "2026-07-01",
        "planned_shipment_date": "2026-07-02",
        "actual_shipment_date": "",
        "courier_transmission_date": "",
        "status_updated_at": "2026-07-02",
        "kaspi_status": "ARCHIVE",
        "kaspi_status_detail": "",
        "internal_status": "COMPLETED",
        "source": "TEST",
        "source_file": "fixture",
        "imported_at": "2026-07-01",
        "updated_at": "2026-07-01",
        "assigned_size": "",
        "size_source": "",
        "size_confidence": "",
        "delivery_cost_for_seller": 100,
        "delivery_cost": 200,
        "returned_to_warehouse": 0,
        "kaspi_article": "",
        "line_identity_key": "L1",
    }
    row.update(overrides)
    columns = list(row)
    placeholders = ",".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO fact_orders_kaspi ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )
    conn.commit()


def test_dedupe_keys_multi_line_order_and_assigned_size_first(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(
        conn,
        order_id="ORD-MULTI",
        kaspi_offer_name="Offer Print",
        sku_id="CL_LINE52_BLACK_M",
        my_size="M",
        assigned_size="XL",
        size_source="GOOGLE_OPS_BOARD",
        line_identity_key="line-a",
    )
    _insert_order(
        conn,
        order_id="ORD-MULTI",
        kaspi_offer_name="Offer Beli",
        sku_key="CL_LINE51_WHITE",
        sku_id="CL_LINE51_WHITE_S",
        my_size="S",
        line_identity_key="line-b",
    )

    result = build_shadow_rows(
        conn,
        from_date="2026-07-01",
        to_date="2026-07-03",
        run_id="test",
    )

    rows = result["rows"]
    assert len(rows) == 2
    first = next(row for row in rows if row["kaspi_offer_name"] == "Offer Print")
    assert first["my_size"] == "XL"
    assert first["sku_id"] == "CL_LINE52_BLACK_XL"
    assert first["final_my_size_source"] == "assigned_size"
    assert first["logical_dedupe_key"] == "ORD-MULTI|ACMEWEAR|Offer Print|CL_LINE52_BLACK|XL"
    assert first["db_unique_key"] == "ORD-MULTI|CL_LINE52_BLACK_XL|ACMEWEAR|Offer Print"
    assert {row["line_identity_key"] for row in rows} == {"line-a", "line-b"}


def test_missing_size_and_unmapped_rows_are_excluded_and_reported(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(conn, order_id="ORD-NO-SIZE", my_size="", assigned_size="", sku_id="", line_identity_key="missing")
    _insert_order(
        conn,
        order_id="ORD-NO-SKU",
        sku_key="UNKNOWN",
        sku_id="",
        my_size="M",
        assigned_size="",
        kaspi_offer_name="Unknown Offer",
        line_identity_key="unmapped",
    )

    result = build_shadow_rows(
        conn,
        from_date="2026-07-01",
        to_date="2026-07-03",
        run_id="test",
    )

    assert result["rows"] == []
    assert result["summary"]["missing_size"] == 1
    reasons = {row["reason"] for row in result["unmapped"]}
    assert "missing_size" in reasons
    assert "unresolved_sku_id" in reasons


def test_apply_mode_refuses_phase1_even_with_env_gate(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = _init_db(db)
    conn.close()
    env = {**os.environ, "AB_DIRECT_FEEDER_APPLY": "1"}

    result = subprocess.run(
        [
            os.sys.executable,
            "scripts/feed_fact_orders_kaspi_to_sales_fact_v2.py",
            "--db",
            str(db),
            "--from-date",
            "2026-07-01",
            "--to-date",
            "2026-07-03",
            "--apply",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Phase 2 not enabled: owner decision retire_crm_excel_pipeline required" in result.stderr

