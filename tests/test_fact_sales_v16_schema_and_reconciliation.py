from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.build_fact_sales_v16_from_api import build_fact_sales_v16_from_api
from scripts.migrate_021_fact_sales_v16 import migrate


def _init_base_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            delivery_cost_for_seller REAL,
            delivery_cost REAL
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            total_price_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER
        );
        """
    )


def test_fact_sales_v16_schema_columns_match_contract(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    sqlite3.connect(str(db)).close()
    migrate(db)
    conn = sqlite3.connect(str(db))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(fact_sales_v16)").fetchall()]
    finally:
        conn.close()
    assert cols == [
        "entry_id",
        "order_id",
        "store_code",
        "offer_id",
        "sku_key",
        "sku_id",
        "quantity",
        "unit_price_kzt",
        "total_price_kzt",
        "delivery_fee_kzt",
        "net_rev_kzt",
        "source",
        "run_id",
        "created_at",
    ]


def test_builder_stops_on_missing_mappings_and_writes_machine_readable_gaps(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    _init_base_tables(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, delivery_cost_for_seller, delivery_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("ORD1", "STOREB", "Offer", None, None, 500.0, 500.0),
    )
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("E1", "ORD1", "STOREB", "ARTICLE-A", 1.0, 15000.0, 15000.0),
            ("E2", "ORD1", "STOREB", "ARTICLE-B", 1.0, 15000.0, 15000.0),
        ],
    )
    conn.commit()
    conn.close()

    migrate(db)
    gaps_path = tmp_path / "gaps.json"

    with pytest.raises(RuntimeError, match="missing mappings"):
        build_fact_sales_v16_from_api(
            db_path=db,
            apply=False,
            run_id="TEST",
            gaps_json_path=gaps_path,
            strict=True,
        )

    payload = json.loads(gaps_path.read_text(encoding="utf-8"))
    assert payload["missing_count"] == 2
    assert {row["entry_id"] for row in payload["missing_entries"]} == {"E1", "E2"}


def test_builder_apply_requires_env_gate(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    _init_base_tables(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, delivery_cost_for_seller, delivery_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("ORD1", "STOREB", "Offer", "SKU_KEY", "SKU_ID", 0.0, 0.0),
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("E1", "ORD1", "STOREB", "ARTICLE-A", 1.0, 15000.0, 15000.0),
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("STOREB", "ARTICLE-A", "SKU_KEY", "SKU_ID", 1),
    )
    conn.commit()
    conn.close()

    migrate(db)
    with pytest.raises(RuntimeError, match="ENABLE_FACT_SALES_V16_WRITE=1"):
        build_fact_sales_v16_from_api(
            db_path=db,
            apply=True,
            run_id="TEST",
            gaps_json_path=tmp_path / "gaps.json",
            strict=True,
        )


def test_builder_apply_reconciles_totals_when_mappings_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    _init_base_tables(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, delivery_cost_for_seller, delivery_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("ORD1", "STOREB", "Offer", None, None, 500.0, 500.0),
    )
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("E1", "ORD1", "STOREB", "ARTICLE-A", 1.0, 15000.0, 15000.0),
            ("E2", "ORD1", "STOREB", "ARTICLE-B", 1.0, 15000.0, 15000.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("STOREB", "ARTICLE-A", "SKU_KEY_A", "SKU_ID_A", 1),
            ("STOREB", "ARTICLE-B", "SKU_KEY_B", "SKU_ID_B", 1),
        ],
    )
    conn.commit()
    conn.close()

    migrate(db)
    monkeypatch.setenv("ENABLE_FACT_SALES_V16_WRITE", "1")
    result = build_fact_sales_v16_from_api(
        db_path=db,
        apply=True,
        run_id="TEST",
        gaps_json_path=tmp_path / "gaps.json",
        strict=True,
    )
    assert result["inserted"] == 2
    assert result["missing"] == 0

    conn = sqlite3.connect(str(db))
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM fact_sales_v16").fetchone()[0]
        total_rev = conn.execute("SELECT SUM(total_price_kzt) FROM fact_sales_v16").fetchone()[0]
        total_fee = conn.execute("SELECT SUM(delivery_fee_kzt) FROM fact_sales_v16").fetchone()[0]
        total_net = conn.execute("SELECT SUM(net_rev_kzt) FROM fact_sales_v16").fetchone()[0]
    finally:
        conn.close()

    assert row_count == 2
    assert total_rev == 30000.0
    assert total_fee == 500.0
    assert total_net == 29500.0


def test_builder_closes_multi_line_gaps_via_offer_history_fallback(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    _init_base_tables(conn)
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, delivery_cost_for_seller, delivery_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD_NEW", "STOREB", "Offer New", None, None, 0.0, 0.0),
            ("ORD_A", "STOREB", "Offer A", "SKU_KEY_A", "SKU_ID_A", 0.0, 0.0),
            ("ORD_B", "STOREB", "Offer B", "SKU_KEY_B", "SKU_ID_B", 0.0, 0.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("E_NEW_A", "ORD_NEW", "STOREB", "ARTICLE-A", 1.0, 10000.0, 10000.0),
            ("E_NEW_B", "ORD_NEW", "STOREB", "ARTICLE-B", 1.0, 12000.0, 12000.0),
            ("E_HIST_A", "ORD_A", "STOREB", "ARTICLE-A", 1.0, 10000.0, 10000.0),
            ("E_HIST_B", "ORD_B", "STOREB", "ARTICLE-B", 1.0, 12000.0, 12000.0),
        ],
    )
    conn.commit()
    conn.close()

    migrate(db)
    result = build_fact_sales_v16_from_api(
        db_path=db,
        apply=False,
        run_id="TEST",
        gaps_json_path=tmp_path / "gaps.json",
        strict=True,
    )
    assert result["missing"] == 0


def test_builder_offer_history_fallback_stops_on_ambiguous_offer(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    _init_base_tables(conn)
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, delivery_cost_for_seller, delivery_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD_NEW", "STOREB", "Offer New", None, None, 0.0, 0.0),
            ("ORD_A", "STOREB", "Offer A", "SKU_KEY_A", "SKU_ID_A", 0.0, 0.0),
            ("ORD_A2", "STOREB", "Offer A2", "SKU_KEY_A2", "SKU_ID_A2", 0.0, 0.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("E_NEW_A", "ORD_NEW", "STOREB", "ARTICLE-A", 1.0, 10000.0, 10000.0),
            ("E_HIST_A", "ORD_A", "STOREB", "ARTICLE-A", 1.0, 10000.0, 10000.0),
            ("E_HIST_A2", "ORD_A2", "STOREB", "ARTICLE-A", 1.0, 10000.0, 10000.0),
        ],
    )
    conn.commit()
    conn.close()

    migrate(db)
    with pytest.raises(RuntimeError, match="missing mappings"):
        build_fact_sales_v16_from_api(
            db_path=db,
            apply=False,
            run_id="TEST",
            gaps_json_path=tmp_path / "gaps.json",
            strict=True,
        )
