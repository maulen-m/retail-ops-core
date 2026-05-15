from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from core.db.ledger import rebuild_snapshot_from_ledger
from scripts.rebuild_snapshot import plan_snapshot_from_ledger


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                active_flag INTEGER
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT,
                my_size TEXT,
                active_flag INTEGER
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY,
                event_date TEXT,
                event_time TEXT,
                event_type TEXT,
                sku_id TEXT,
                sku_key TEXT,
                my_size TEXT,
                qty_change INTEGER,
                store_code TEXT,
                reference_id TEXT,
                notes TEXT
            );
            CREATE TABLE exception_queue (
                exception_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE fact_inventory_snapshot_size (
                id INTEGER PRIMARY KEY,
                sku_id TEXT,
                sku_key TEXT,
                my_size TEXT,
                current_stock INTEGER,
                inbound_stock INTEGER,
                snapshot_date TEXT
            );
            """
        )


def _insert_negative_with_exception(path: Path, *, sku_id: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, 1)",
            ("CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK",),
        )
        conn.execute(
            """
            INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag)
            VALUES (?, ?, ?, 1)
            """,
            (sku_id, "CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK", "BLACK"),
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_time, event_type, sku_id, sku_key, my_size,
                qty_change, store_code, reference_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-15",
                "2026-04-16 05:13:50",
                "SALE",
                sku_id,
                "CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK",
                "BLACK",
                -1,
                "UNIVERSAL",
                "889190849",
                "sales_fact_v2 stock replay SALE",
            ),
        )
        conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, domain, severity, status, reason, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "AGENT6_STOCK_REBUILD_20PCT_20260503:"
                "NEGATIVE_RAW_LEDGER_BALANCE:CL_NEW_CLO_MEN_BERSERK_RUSH_BLACK",
                "STOCK",
                "HIGH",
                "OPEN",
                "NEGATIVE_RAW_LEDGER_BALANCE: owner accepted active-zero quarantine",
                json.dumps({"sku_id": sku_id}),
            ),
        )
        conn.commit()


def test_plan_snapshot_clamps_exact_owner_accepted_negative_to_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _insert_negative_with_exception(db_path, sku_id="CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK")

    planned = plan_snapshot_from_ledger(
        snapshot_date=date(2026, 5, 4),
        store_code="UNIVERSAL",
        db_path=db_path,
    )

    assert planned["CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK"]["current_stock"] == 0


def test_apply_snapshot_clamps_exact_owner_accepted_negative_to_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _insert_negative_with_exception(db_path, sku_id="CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK")

    rebuild_snapshot_from_ledger(
        snapshot_date=date(2026, 5, 4),
        store_code="UNIVERSAL",
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        current_stock = conn.execute(
            """
            SELECT current_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date='2026-05-04'
              AND sku_id='CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK'
            """
        ).fetchone()[0]

    assert current_stock == 0
