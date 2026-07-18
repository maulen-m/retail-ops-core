from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.repair_stock_ledger_mechanical_replays import (
    build_mechanical_repair_plan,
    repair_stock_ledger_mechanical_replays,
)


BATCH_START = "2026-07-03 16:27:00"
BATCH_END = "2026-07-03 16:29:59"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT,
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT,
            created_by TEXT,
            created_at TEXT,
            idempotency_key TEXT
        );
        CREATE TABLE fact_po_lines (
            id INTEGER PRIMARY KEY,
            po_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            received_qty INTEGER,
            actual_arrival_date TEXT,
            status TEXT
        );
        CREATE TABLE po_line (
            po_id TEXT NOT NULL,
            po_part_id TEXT,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL
        );
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT,
            return_flag INTEGER DEFAULT 0
        );
        CREATE TABLE fact_order_entry_header_only_source_gap_quarantine (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            publication_exclusion_required INTEGER NOT NULL,
            product_stock_excluded INTEGER NOT NULL,
            active_flag INTEGER NOT NULL
        );
        CREATE TABLE fact_order_entry_product_identity_quarantine (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            publication_exclusion_required INTEGER NOT NULL,
            product_stock_excluded INTEGER NOT NULL,
            active_flag INTEGER NOT NULL
        );
        """
    )
    return conn


def _seed_fixture(path: Path) -> None:
    conn = _connect(path)
    conn.execute(
        "INSERT INTO fact_po_lines VALUES "
        "(1,'PO-1','UNIVERSAL','SKU_A','SKU_A_M','M',5,'2026-01-14','DELIVERED')"
    )
    conn.execute(
        "INSERT INTO po_line VALUES ('PO-1','PO-1.0','SKU_A_M','M')"
    )
    ledger_rows = [
        ("2026-01-14", "INBOUND", "SKU_A", "SKU_A_M", "M", 5, "PO-1.0", "PO_PART", "", "", "SYSTEM", "system", "2026-01-17 10:00:00", "po-part-1"),
        ("2026-01-14", "INBOUND", "SKU_A", "SKU_A_M", "M", 5, "PO-1", "PO", "", "Backfill PO arrival from fact_po_lines", "SYSTEM", "system", "2026-07-03 16:29:33", None),
        ("2026-07-01", "SALE", "SKU_Q", "SKU_Q_M", "M", -1, "Q-1", "SALE", "Offer Q", "", "IMPORT", "system", "2026-07-03 16:27:20", None),
        ("2026-06-20", "SALE", "SKU_S", "SKU_S_M", "M", -1, "O-1", "SALE", "Offer S", "", "IMPORT", "system", "2026-06-20 10:00:00", None),
        ("2026-06-20", "SALE", "SKU_S", "SKU_S_M", "M", -1, "O-1", "SALE", "Offer S", "", "IMPORT", "system", "2026-07-03 16:27:21", None),
        ("2026-06-21", "SALE", "SKU_U", "SKU_U_M", "M", -1, "NO-SOURCE", "SALE", "Offer U", "", "IMPORT", "system", "2026-06-21 10:00:00", None),
        ("2026-06-21", "SALE", "SKU_U", "SKU_U_M", "M", -1, "NO-SOURCE", "SALE", "Offer U", "", "IMPORT", "system", "2026-07-03 16:27:22", None),
    ]
    conn.executemany(
        """
        INSERT INTO stock_ledger (
            event_date,event_type,sku_key,sku_id,my_size,store_code,qty_change,
            reference_id,reference_type,kaspi_offer_name,notes,input_source,created_by,created_at,
            idempotency_key
        ) VALUES (?,?,?,?,?,'UNIVERSAL',?,?,?,?,?,?,?,?,?)
        """,
        ledger_rows,
    )
    conn.execute(
        "INSERT INTO fact_order_entry_header_only_source_gap_quarantine "
        "VALUES ('STOREB','Q-1',1,1,1)"
    )
    conn.execute(
        "INSERT INTO sales_fact_v2 VALUES "
        "(1,'O-1','2026-06-20','SKU_S','SKU_S_M','M','Offer S','ACMEWEAR',1,'DELIVERED',0)"
    )
    conn.commit()
    conn.close()


def test_plan_separates_three_proven_mechanical_populations(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_fixture(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    plan = build_mechanical_repair_plan(
        conn,
        batch_created_start=BATCH_START,
        batch_created_end=BATCH_END,
    )

    assert plan["summary"]["po_replay_rows"] == 1
    assert plan["summary"]["quarantine_leak_rows"] == 1
    assert plan["summary"]["sale_replay_rows"] == 1
    assert plan["summary"]["candidate_rows"] == 3
    assert {row["ledger_id"] for row in plan["candidates"]} == {2, 3, 5}
    assert any(row["reason"] == "SALE_REPLAY_SOURCE_MISSING" for row in plan["unresolved"])


def test_apply_is_backup_first_and_exactly_deletes_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_fixture(db_path)
    output_root = tmp_path / "evidence"

    dry = repair_stock_ledger_mechanical_replays(
        db_path=db_path,
        output_root=output_root / "dry",
        batch_created_start=BATCH_START,
        batch_created_end=BATCH_END,
        apply=False,
    )
    applied = repair_stock_ledger_mechanical_replays(
        db_path=db_path,
        output_root=output_root / "apply",
        batch_created_start=BATCH_START,
        batch_created_end=BATCH_END,
        apply=True,
        env_gate_value="1",
        expected_pre_sha256=dry["pre_sha256"],
        expected_candidate_rows=3,
        expected_candidate_id_hash=dry["candidate_id_hash"],
    )

    assert applied["applied"] is True
    assert applied["deleted_rows"] == 3
    assert Path(applied["backup_path"]).exists()
    assert applied["integrity_check"]["backup"] == "ok"
    assert applied["integrity_check"]["after"] == "ok"
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0] == 4
    assert conn.execute(
        "SELECT COUNT(*) FROM stock_ledger WHERE ledger_id IN (2,3,5)"
    ).fetchone()[0] == 0
    running_rows = conn.execute(
        "SELECT ledger_id, running_balance FROM stock_ledger WHERE ledger_id IN (1,4) "
        "ORDER BY ledger_id"
    ).fetchall()
    assert running_rows == [(1, 5), (4, -1)]
    conn.close()


def test_sale_replay_requires_exact_source_date_size_offer_and_quantity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_fixture(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE sales_fact_v2 SET kaspi_offer_name='Different Offer'")
    conn.commit()
    conn.row_factory = sqlite3.Row

    plan = build_mechanical_repair_plan(
        conn,
        batch_created_start=BATCH_START,
        batch_created_end=BATCH_END,
    )

    assert plan["summary"]["sale_replay_rows"] == 0
    assert 5 not in {row["ledger_id"] for row in plan["candidates"]}
    assert any(
        row["reason"] == "SALE_REPLAY_SOURCE_MISSING"
        and row.get("reference_id") == "O-1"
        for row in plan["unresolved"]
    )
