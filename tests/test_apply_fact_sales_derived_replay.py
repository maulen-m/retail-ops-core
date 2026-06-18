from __future__ import annotations

from datetime import date
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.apply_fact_sales_derived_replay import (
    ENV_GATE,
    FactSalesReplayError,
    _sha256_file,
    run_replay,
)


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            product_type TEXT,
            cogs_kzt REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            size_order INTEGER
        );
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            kaspi_offer_name TEXT,
            store_code TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL NOT NULL,
            product_type TEXT NOT NULL,
            channel TEXT,
            delivery_fee REAL NOT NULL,
            net_rev_unit REAL NOT NULL,
            line_net_rev REAL NOT NULL,
            cogs_unit REAL NOT NULL,
            cogs_line REAL NOT NULL,
            profit_unit REAL NOT NULL,
            profit_line REAL NOT NULL,
            channel_code TEXT,
            UNIQUE(order_id, kaspi_offer_name, sku_id, store_code)
        );
        CREATE TABLE fact_sales_daily (
            sale_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            units INTEGER NOT NULL,
            revenue REAL,
            cogs REAL,
            profit REAL,
            UNIQUE(sale_date, store_code, sku_key)
        );
        CREATE TABLE fact_sales_daily_size (
            sale_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            units INTEGER NOT NULL,
            UNIQUE(sale_date, store_code, sku_id)
        );
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            quantity INTEGER
        );
        CREATE TABLE fact_cashflow_daily (
            date TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO dim_sku VALUES ('CL_TEST_BLACK', 10.0, 0.5, 'CL', NULL)"
    )
    conn.execute(
        "INSERT INTO dim_sku_size VALUES ('CL_TEST_BLACK_M', 'CL_TEST_BLACK', 'M', 2)"
    )
    conn.execute(
        """
        INSERT INTO fact_sales (
            order_id, kaspi_offer_name, store_code, order_date, sku_key, sku_id,
            my_size, quantity, sell_price_kzt, product_type, channel, delivery_fee,
            net_rev_unit, line_net_rev, cogs_unit, cogs_line, profit_unit, profit_line, channel_code
        ) VALUES (
            'OLD-1', 'Old Offer', 'UNIVERSAL', '2026-04-15', 'CL_TEST_BLACK',
            'CL_TEST_BLACK_M', 'M', 1, 15000.0, 'CL', 'Kaspi', 100.0,
            14000.0, 14000.0, 500.0, 500.0, 13500.0, 13500.0, 'KSP'
        )
        """
    )
    conn.execute(
        "INSERT INTO fact_sales_daily VALUES ('2026-04-15', 'UNIVERSAL', 'CL_TEST_BLACK', 1, 14000.0, 500.0, 13500.0)"
    )
    conn.execute(
        "INSERT INTO fact_sales_daily_size VALUES ('2026-04-15', 'UNIVERSAL', 'CL_TEST_BLACK_M', 1)"
    )
    conn.execute("INSERT INTO sales_fact_v2 VALUES ('NEW-1', '2026-06-13', 1)")
    conn.execute("INSERT INTO fact_cashflow_daily VALUES ('2026-06-13')")
    conn.commit()
    conn.close()


def _write_crm(path: Path) -> None:
    df = pd.DataFrame(
        {
            "OrderID": ["OLD-1", "NEW-1"],
            "Date": [date(2026, 4, 15), date(2026, 6, 13)],
            "KASPI_OFFER_NAME": ["Old Offer", "New Offer"],
            "SKU_ID": ["CL_TEST_BLACK_M", "CL_TEST_BLACK_M"],
            "SKU_key": ["CL_TEST_BLACK", "CL_TEST_BLACK"],
            "MY_SIZE": ["M", "M"],
            "Quantity": [1, 1],
            "Sell_price_kzt": [15000.0, 15000.0],
            "STORE_NAME": ["Universal", "Universal"],
            "Return": [0, 0],
        }
    )
    df.to_excel(path, sheet_name="SALES_KSP_CRM_1", index=False)


def _fact_sales_orders(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    rows = [row[0] for row in conn.execute("SELECT order_id FROM fact_sales ORDER BY order_id")]
    conn.close()
    return rows


def test_dry_run_uses_simulation_db_and_does_not_mutate_source(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    crm = tmp_path / "crm.xlsx"
    _seed_db(db)
    _write_crm(crm)

    pre_sha = _sha256_file(db)
    report = run_replay(
        db_path=db,
        crm_path=crm,
        output_dir=tmp_path / "dry_run",
        as_of=date(2026, 6, 14),
    )

    assert report["status"] == "DRY_RUN"
    assert report["replay"]["fact_sales"]["inserted"] == 1
    assert report["source_db_sha256_changed"] is False
    assert _sha256_file(db) == pre_sha
    assert _fact_sales_orders(db) == ["OLD-1"]


def test_apply_requires_env_gate_and_backup_dir(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    crm = tmp_path / "crm.xlsx"
    _seed_db(db)
    _write_crm(crm)

    with pytest.raises(FactSalesReplayError, match=ENV_GATE):
        run_replay(
            db_path=db,
            crm_path=crm,
            output_dir=tmp_path / "missing_gate",
            backup_dir=tmp_path / "backups",
            as_of=date(2026, 6, 14),
            apply=True,
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(ENV_GATE, "1")
        with pytest.raises(FactSalesReplayError, match="--backup-dir"):
            run_replay(
                db_path=db,
                crm_path=crm,
                output_dir=tmp_path / "missing_backup",
                as_of=date(2026, 6, 14),
                apply=True,
            )


def test_apply_enforces_pre_sha_and_replays_only_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    crm = tmp_path / "crm.xlsx"
    _seed_db(db)
    _write_crm(crm)
    monkeypatch.setenv(ENV_GATE, "1")

    with pytest.raises(FactSalesReplayError, match="pre-SHA mismatch"):
        run_replay(
            db_path=db,
            crm_path=crm,
            output_dir=tmp_path / "wrong_sha",
            backup_dir=tmp_path / "backups_wrong",
            as_of=date(2026, 6, 14),
            expected_pre_sha256="0" * 64,
            apply=True,
        )

    report = run_replay(
        db_path=db,
        crm_path=crm,
        output_dir=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        as_of=date(2026, 6, 14),
        expected_pre_sha256=_sha256_file(db),
        apply=True,
    )

    assert report["status"] == "APPLIED"
    assert Path(report["backup_path"]).exists()
    assert report["window"] == {"from_date": "2026-04-16", "to_date": "2026-06-13"}
    assert report["target_after"]["fact_sales_max_date"] == "2026-06-13"
    assert report["validation"]["ok"] is True
    assert _fact_sales_orders(db) == ["NEW-1", "OLD-1"]


def test_replay_falls_back_to_fresh_sales_fact_v2_when_crm_window_is_blank(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    crm = tmp_path / "crm.xlsx"
    _seed_db(db)
    _write_crm(crm)

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        DROP TABLE sales_fact_v2;
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity INTEGER,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, sell_price_kzt, delivery_fee, cogs, net_rev,
            profit, status, return_flag
        ) VALUES (
            'V2-ONLY', '2026-06-15', 'CL_TEST_BLACK', 'CL_TEST_BLACK_M', 'M',
            'Fresh v2 offer', 'UNIVERSAL', 1, 15000.0, 100.0, NULL, 14900.0,
            NULL, 'DELIVERED', 0
        );
        INSERT INTO fact_cashflow_daily VALUES ('2026-06-15');
        """
    )
    conn.commit()
    conn.close()

    report = run_replay(
        db_path=db,
        crm_path=crm,
        output_dir=tmp_path / "dry_run_v2_fallback",
        from_date="2026-06-14",
        to_date="2026-06-15",
        as_of=date(2026, 6, 15),
    )

    assert report["status"] == "DRY_RUN"
    assert report["replay"]["fact_sales"]["inserted"] == 0
    assert report["replay"]["sales_fact_v2_fallback"]["inserted"] == 1
    assert report["target_after"]["fact_sales_max_date"] == "2026-06-15"
    assert report["target_after"]["fact_sales_daily_max_date"] == "2026-06-15"
    target = sqlite3.connect(report["target_db_path"])
    try:
        assert target.execute(
            "SELECT COUNT(*) FROM fact_sales WHERE order_id = 'V2-ONLY'"
        ).fetchone()[0] == 1
    finally:
        target.close()
