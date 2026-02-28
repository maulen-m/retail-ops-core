from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.validate_sales_engine_self_sufficient import validate_sales_engine_self_sufficient


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity REAL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            ingested_at TEXT,
            source_file TEXT,
            api_updated_at TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            assigned_size TEXT,
            my_size TEXT,
            quantity INTEGER,
            internal_status TEXT,
            kaspi_status TEXT,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            created_at TEXT,
            delivery_cost REAL,
            delivery_cost_for_seller REAL
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            total_price_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER
        );
        """
    )


def _seed_data(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-SELF', 'ACMEWEAR', 'OFFER-SELF', 'SKU_SELF', 'SKU_SELF_L', 'L', 'M',
            1, 'COMPLETED', 'Выдан', '2026-02-25T11:00:00',
            '2026-02-25', '2026-02-25', '2026-02-24', 30
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E-SELF', 'ORD-SELF', 'ACMEWEAR', 'OFFER-SELF', 1, 1000)
        """
    )
    conn.commit()


def test_self_sufficient_validator_writes_report_and_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    _seed_data(conn)
    conn.close()

    ocean = tmp_path / "ocean.csv"
    ocean.write_text("order_id,store_code\nORD-SELF,ACMEWEAR\n", encoding="utf-8")

    def fake_parity(**_kwargs):
        return {"status": "PASS", "nonvolatile_mismatch_count": 0}

    monkeypatch.setattr(
        "scripts.validate_sales_engine_self_sufficient.validate_sales_truth_ocean_drop_parity",
        fake_parity,
    )

    report = validate_sales_engine_self_sufficient(
        db_path=db,
        as_of=date(2026, 2, 26),
        ocean_drop_path=ocean,
        output_root=tmp_path / "out",
        strict=True,
        crm_archive_lookup_path=None,
        window_days=14,
    )

    assert report["ok"] is True
    assert report["status"] == "PASS"
    assert Path(report["json_path"]).exists()
    payload = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert payload["rows_applied"] >= 1
    assert payload["nonvolatile_mismatch_count"] == 0
    assert payload["window_days"] == 14


def test_self_sufficient_validator_fails_closed_on_parity_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    _seed_data(conn)
    conn.close()

    ocean = tmp_path / "ocean.csv"
    ocean.write_text("order_id,store_code\nORD-SELF,ACMEWEAR\n", encoding="utf-8")

    def fake_parity(**_kwargs):
        raise RuntimeError("parity failed")

    monkeypatch.setattr(
        "scripts.validate_sales_engine_self_sufficient.validate_sales_truth_ocean_drop_parity",
        fake_parity,
    )

    with pytest.raises(RuntimeError, match="self-sufficient"):
        validate_sales_engine_self_sufficient(
            db_path=db,
            as_of=date(2026, 2, 26),
            ocean_drop_path=ocean,
            output_root=tmp_path / "out",
            strict=True,
            crm_archive_lookup_path=None,
            window_days=14,
        )
