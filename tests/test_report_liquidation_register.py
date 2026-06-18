from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.report_liquidation_register import build_liquidation_register_report


def _write_db(
    path: Path,
    *,
    snapshot_rows: list[dict[str, object]],
    sales_rows: list[dict[str, object]] | None = None,
    dim_rows: list[dict[str, object]] | None = None,
) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(snapshot_date, sku_id)
        );
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
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            color TEXT,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            category TEXT,
            gender TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            cogs_kzt REAL,
            avg_sell_price_kzt_used REAL,
            avg_sell_price_source TEXT,
            price_missing_flag INTEGER
        );
        """
    )
    for row in dim_rows or []:
        conn.execute(
            """
            INSERT INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg,
                category, gender, active_flag, cogs_kzt
            )
            VALUES (
                :sku_key, :model, :color, :product_type, :base_cost_cny, :weight_kg,
                :category, :gender, :active_flag, :cogs_kzt
            )
            """,
            row,
        )
    for row in snapshot_rows:
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            )
            VALUES (
                :snapshot_date, :sku_id, :sku_key, :my_size, :current_stock, :inbound_stock
            )
            """,
            row,
        )
    for row in sales_rows or []:
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, status
            )
            VALUES (
                :order_id, :order_date, :sku_key, :sku_id, :my_size,
                :kaspi_offer_name, :store_code, :quantity, :status
            )
            """,
            row,
        )
    conn.commit()
    conn.close()


def _dim(sku_key: str, cogs_kzt: float | None = 100.0) -> dict[str, object]:
    return {
        "sku_key": sku_key,
        "model": sku_key,
        "color": "BLACK",
        "product_type": "CL",
        "base_cost_cny": 1,
        "weight_kg": 1,
        "category": "TEST",
        "gender": "MEN",
        "active_flag": 1,
        "cogs_kzt": cogs_kzt,
    }


def _stock(
    sku_key: str,
    *,
    sku_id: str | None = None,
    size: str = "XL",
    snapshot_date: str = "2026-06-17",
    stock: int = 10,
) -> dict[str, object]:
    return {
        "snapshot_date": snapshot_date,
        "sku_id": sku_id or f"{sku_key}_{size}",
        "sku_key": sku_key,
        "my_size": size,
        "current_stock": stock,
        "inbound_stock": 0,
    }


def _sale(
    sku_key: str,
    *,
    order_id: str,
    size: str = "XL",
    quantity: int = 1,
    order_date: str = "2026-06-16",
    status: str = "DELIVERED",
) -> dict[str, object]:
    return {
        "order_id": order_id,
        "order_date": order_date,
        "sku_key": sku_key,
        "sku_id": f"{sku_key}_{size}",
        "my_size": size,
        "kaspi_offer_name": sku_key,
        "store_code": "UNIVERSAL",
        "quantity": quantity,
        "status": status,
    }


def _write_config(path: Path, *, db_path: Path, slow_cover_days: int = 90) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "LIQUIDATION_REGISTER_V1",
                "gate_id": "G-LIQ-01",
                "owner_decision_ids": ["OD-005", "OD-011", "OD-018"],
                "db_path": str(db_path),
                "max_basis_age_days": 2,
                "delivered_statuses": ["DELIVERED"],
                "non_cancelled_excluded_status_tokens": ["CANCEL"],
                "zero_velocity_window_days": 30,
                "size_misallocation_window_days": 90,
                "slow_cover_days": slow_cover_days,
                "count_gated_sku_keys": ["CL_OC_MEN_LINE51_WHITE"],
                "canonical_tranche1_sku_keys": ["SKU_ZERO"],
                "movement_watch_sku_keys": ["SKU_SLOW"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_fresh_register_segments_are_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(
        db,
        dim_rows=[
            _dim("CL_OC_MEN_LINE51_WHITE", 6006.76),
            _dim("SKU_ZERO", 100),
            _dim("SKU_SLOW", 10),
            _dim("SKU_ACTIVE", 50),
        ],
        snapshot_rows=[
            _stock("CL_OC_MEN_LINE51_WHITE", stock=12),
            _stock("SKU_ZERO", stock=4),
            _stock("SKU_SLOW", stock=100),
            _stock("SKU_ACTIVE", stock=3),
        ],
        sales_rows=[
            _sale("SKU_SLOW", order_id="slow-1", quantity=10),
            _sale("SKU_ACTIVE", order_id="active-1", quantity=30),
        ],
    )
    _write_config(config, db_path=db)

    report = build_liquidation_register_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["latest_snapshot_date"] == "2026-06-17"
    assert report["snapshot_age_days"] == 1
    by_sku = {
        row["sku_key"]: row
        for row in _read_csv(tmp_path / "out" / "liquidation_segment_map.csv")
    }
    assert by_sku["CL_OC_MEN_LINE51_WHITE"]["segment"] == "A_COUNT_GATED"
    assert by_sku["SKU_ZERO"]["segment"] == "B_ZERO_VELOCITY"
    assert by_sku["SKU_SLOW"]["segment"] == "C_SLOW_HIGH_COVER"
    assert by_sku["SKU_ACTIVE"]["segment"] == "E_STRATEGIC_NO_ACTION"


def test_stale_snapshot_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(
        db,
        dim_rows=[_dim("SKU_ZERO")],
        snapshot_rows=[_stock("SKU_ZERO", snapshot_date="2026-06-10", stock=10)],
    )
    _write_config(config, db_path=db)

    report = build_liquidation_register_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any(row["check"] == "snapshot_basis_fresh" and not row["ok"] for row in report["checks"])


def test_size_misallocated_segment_is_d_when_cover_not_slow(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(
        db,
        dim_rows=[_dim("SKU_SIZE")],
        snapshot_rows=[
            _stock("SKU_SIZE", sku_id="SKU_SIZE_S", size="S", stock=2),
            _stock("SKU_SIZE", sku_id="SKU_SIZE_M", size="M", stock=2),
        ],
        sales_rows=[_sale("SKU_SIZE", order_id="size-1", size="M", quantity=2)],
    )
    _write_config(config, db_path=db, slow_cover_days=999)

    report = build_liquidation_register_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    by_sku = {
        row["sku_key"]: row
        for row in _read_csv(tmp_path / "out" / "liquidation_segment_map.csv")
    }
    assert by_sku["SKU_SIZE"]["segment"] == "D_SIZE_MISALLOCATED"


def test_missing_cogs_exposed_as_hold_without_inventing_value(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(
        db,
        dim_rows=[_dim("SKU_NO_COGS", None)],
        snapshot_rows=[_stock("SKU_NO_COGS", stock=5)],
    )
    _write_config(config, db_path=db)

    report = build_liquidation_register_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["missing_cogs_positive_size_rows"] == 1
    row = _read_csv(tmp_path / "out" / "liquidation_register.csv")[0]
    assert row["goods_basis_kzt_known_cogs"] == "0.00"
    assert row["tranche_sizing_allowed"] == "False"
    assert row["hold_reason"] == "missing_positive_stock_cogs"


def _read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
