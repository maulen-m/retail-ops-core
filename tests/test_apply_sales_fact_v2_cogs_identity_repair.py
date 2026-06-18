from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts.apply_sales_fact_v2_cogs_identity_repair import (
    ENV_GATE,
    SalesIdentityRepairError,
    _sha256_file,
    run_repair,
)


def _seed_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
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
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            product_id TEXT,
            offer_id TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            total_price_kzt REAL,
            raw_json TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            assigned_size TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            color TEXT,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            cogs_kzt REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            active_flag INTEGER DEFAULT 1
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        );
        CREATE VIEW view_sales_line_truth AS
        SELECT
            order_id,
            date(order_date) AS sale_date,
            store_code,
            sku_key,
            NULL AS cogs_kzt
        FROM sales_fact_v2
        WHERE sku_key IN ('CL', '116515378', '132822924');
        """
    )
    conn.commit()
    conn.close()


def _add_ready_sku(conn: sqlite3.Connection, sku_key: str, *sizes: str) -> None:
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES (?, 'MODEL', 'BLACK', 'CL', 47.0, 0.95, 3666.0)
        """,
        (sku_key,),
    )
    for size in sizes:
        conn.execute(
            "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
            (f"{sku_key}_{size}", sku_key, size),
        )


def _sales_rows(db_path: Path) -> list[tuple[int, str, str, str]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT sale_id, sku_key, sku_id, my_size FROM sales_fact_v2 ORDER BY sale_id"
    ).fetchall()
    conn.close()
    return [(int(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in rows]


def test_dry_run_uses_simulation_db_and_keeps_source_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_schema(db)
    conn = sqlite3.connect(db)
    _add_ready_sku(conn, "CL_OC_MEN_LINE52_BLACK", "L")
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, net_rev, status, return_flag
        ) VALUES ('1', '2026-03-01', 'CL', 'CL_L', 'L', 'Print black L', 'UNIVERSAL', 1, 7000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id)
        VALUES ('e1', '1', 'UNIVERSAL', 'PRINT_OFFER_L')
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (
            store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id
        ) VALUES (
            'UNIVERSAL', 'PRINT_OFFER_L', 'Print black L',
            'CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK_L'
        )
        """
    )
    conn.commit()
    conn.close()
    before = _sha256_file(db)

    report = run_repair(db_path=db, output_dir=tmp_path / "dry")

    assert report["status"] == "DRY_RUN"
    assert report["candidate_count"] == 1
    assert report["rows_updated"] == 1
    assert report["db_sha256_changed"] is False
    assert _sha256_file(db) == before
    assert _sales_rows(db) == [(1, "CL", "CL_L", "L")]


def test_apply_requires_env_gate_and_backup_dir(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_schema(db)

    with pytest.raises(SalesIdentityRepairError, match=ENV_GATE):
        run_repair(db_path=db, output_dir=tmp_path / "missing_gate", backup_dir=tmp_path / "backups", apply=True)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(ENV_GATE, "1")
        with pytest.raises(SalesIdentityRepairError, match="--backup-dir"):
            run_repair(db_path=db, output_dir=tmp_path / "missing_backup", apply=True)


def test_apply_updates_exact_identity_and_honors_expected_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    _seed_schema(db)
    conn = sqlite3.connect(db)
    _add_ready_sku(conn, "CL_OC_MEN_LINE52_BLACK", "XL")
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, net_rev, status, return_flag
        ) VALUES ('2', '2026-03-02', 'CL', 'CL_XL', 'XL', 'Print black XL', 'UNIVERSAL', 1, 7000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        "INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id) VALUES ('e2', '2', 'UNIVERSAL', 'CL_OC_MEN_LINE52_BLACK_ABC_(XL)')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv(ENV_GATE, "1")

    with pytest.raises(SalesIdentityRepairError, match="candidate count mismatch"):
        run_repair(
            db_path=db,
            output_dir=tmp_path / "wrong_count",
            backup_dir=tmp_path / "backups_wrong",
            expected_count=2,
            apply=True,
        )
    assert _sales_rows(db) == [(1, "CL", "CL_XL", "XL")]

    report = run_repair(
        db_path=db,
        output_dir=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256_file(db),
        expected_count=1,
        apply=True,
    )

    assert report["status"] == "APPLIED"
    assert Path(str(report["backup_path"])).exists()
    assert _sales_rows(db) == [(1, "CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_XL", "XL")]


def test_duplicate_collision_can_split_by_existing_sales_row_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    _seed_schema(db)
    conn = sqlite3.connect(db)
    _add_ready_sku(conn, "CL_OC_MEN_LINE52_BLACK", "M", "L")
    for sku_id, my_size, order_date in [
        ("CL_M", "M", "2026-03-19"),
        ("CL_L", "L", "2026-03-20"),
    ]:
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, status, return_flag
            ) VALUES ('861506861', ?, 'CL', ?, ?, 'Print black M', 'UNIVERSAL', 1, 7000, 'DELIVERED', 0)
            """,
            (order_date, sku_id, my_size),
        )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id)
        VALUES ('e3', '861506861', 'UNIVERSAL', 'CL_OC_MEN_LINE52_BLACK_116155651_46-48_(L)')
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv(ENV_GATE, "1")

    report = run_repair(
        db_path=db,
        output_dir=tmp_path / "apply_split",
        backup_dir=tmp_path / "backups",
        expected_count=2,
        apply=True,
    )

    assert report["by_source"] == {"ready_prefix_duplicate_split_by_sales_row_size": 2}
    assert _sales_rows(db) == [
        (1, "CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_M", "M"),
        (2, "CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_L", "L"),
    ]
