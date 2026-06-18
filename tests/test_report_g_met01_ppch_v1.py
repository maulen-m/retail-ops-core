from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.report_g_met01_ppch_v1 import build_ppch_v1_report


def _write_db(path: Path, *, snapshot_date: str = "2026-06-17", qc_rows: int = 0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL
        );
        CREATE TABLE view_sales_line_truth (
            order_id TEXT,
            sale_date TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            units REAL,
            net_rev_kzt REAL,
            cogs_kzt REAL,
            profit_kzt REAL
        );
        CREATE TABLE ads_spend_sidecar_daily_sku (
            date TEXT,
            store_code TEXT,
            sku_key TEXT,
            ads_cost_kzt REAL
        );
        CREATE TABLE return_qc_event (
            qc_event_id TEXT PRIMARY KEY,
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            qc_status TEXT NOT NULL,
            qc_ts TEXT,
            accepted_active_qty INTEGER NOT NULL DEFAULT 0,
            quarantine_qty INTEGER NOT NULL DEFAULT 0,
            rejected_qty INTEGER NOT NULL DEFAULT 0,
            writeoff_qty INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO dim_sku(sku_key, cogs_kzt) VALUES (?, ?)",
        [("SKU_A", 100.0), ("SKU_B", 200.0)],
    )
    conn.executemany(
        """
        INSERT INTO fact_inventory_snapshot_size(
            snapshot_date, sku_id, sku_key, my_size, current_stock
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (snapshot_date, "SKU_A_S", "SKU_A", "S", 10),
            (snapshot_date, "SKU_B_M", "SKU_B", "M", 5),
        ],
    )
    conn.executemany(
        """
        INSERT INTO view_sales_line_truth(
            order_id, sale_date, store_code, sku_key, sku_id, my_size,
            units, net_rev_kzt, cogs_kzt, profit_kzt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("1", "2026-06-10", "UNIVERSAL", "SKU_A", "SKU_A_S", "S", 1, 1000.0, 100.0, 300.0),
            ("2", "2026-06-16", "UNIVERSAL", "SKU_B", "SKU_B_M", "M", 1, 1200.0, 200.0, 400.0),
        ],
    )
    conn.execute(
        "INSERT INTO ads_spend_sidecar_daily_sku(date, store_code, sku_key, ads_cost_kzt) VALUES (?, ?, ?, ?)",
        ("2026-06-10", "UNIVERSAL", "SKU_A", 50.0),
    )
    for index in range(qc_rows):
        conn.execute(
            """
            INSERT INTO return_qc_event(
                qc_event_id, store_code, order_id, sku_id, quantity, qc_status,
                qc_ts, source, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"qc-{index}",
                "UNIVERSAL",
                f"order-{index}",
                "SKU_A_S",
                1,
                "PASS",
                "2026-06-12T12:00:00+05:00",
                "test",
                f"idem-{index}",
            ),
        )
    conn.commit()
    conn.close()


def _write_config(path: Path, *, db_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "PPCH_V1_METRIC_V1",
                "gate_id": "G-MET-01",
                "db_path": str(db_path),
                "denominator_basis": "capitalized_rows_basis",
                "max_denominator_snapshot_age_days": 7,
                "period": "month_to_latest_sales",
                "headline_policy": {
                    "green_requires_return_qc_event": True,
                    "interim_when_return_qc_missing": "v0.75",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_fresh_denominator_without_return_qc_is_armed(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_config(config, db_path=db)

    report = build_ppch_v1_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:10:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["denominator_basis"] == "capitalized_rows_basis"
    assert report["denominator_snapshot_age_days"] == 1
    assert report["return_qc_event_count"] == 0
    assert report["ppch_v1"]["mid_pct_30d"] is not None
    assert report["headline_status"] == "interim_v0.75_until_return_qc_measured"


def test_stale_denominator_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db, snapshot_date="2026-06-01")
    _write_config(config, db_path=db)

    report = build_ppch_v1_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:10:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("denominator_snapshot_fresh" in blocker for blocker in report["blockers"])


def test_measured_return_qc_allows_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db, qc_rows=1)
    _write_config(config, db_path=db)

    report = build_ppch_v1_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:10:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["return_qc_event_count"] == 1
    assert report["headline_status"] == "ppch_v1_owner_headline_ready"
