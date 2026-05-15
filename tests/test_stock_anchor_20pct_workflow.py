from __future__ import annotations

import sqlite3
from pathlib import Path

from core.ops.stock_anchor_20pct import (
    BASELINE_REFERENCE_TYPE,
    STOCK_ANCHOR_REFERENCE_TYPE,
    AnchorStockRow,
    apply_anchor_and_adjustment_events,
    build_anchor_lineage_snapshot,
    build_high_risk_exception_specs,
    build_offer_availability_rows,
    compute_adjustment_plan,
)


def _make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE stock_anchor (
            anchor_id TEXT PRIMARY KEY,
            anchor_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            total_units INTEGER NOT NULL DEFAULT 0,
            approved_by TEXT,
            approved_at TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE stock_adjustment_batch (
            batch_id TEXT PRIMARY KEY,
            anchor_id TEXT NOT NULL,
            method TEXT NOT NULL,
            method_version TEXT NOT NULL,
            reduction_rate REAL,
            target_units_delta INTEGER,
            generated_units_delta INTEGER,
            dry_run_report_path TEXT,
            approved_by TEXT,
            approved_at TEXT,
            applied_at TEXT,
            rollback_batch_id TEXT,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_time TEXT DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            idempotency_key TEXT
        );
        CREATE UNIQUE INDEX ux_stock_ledger_idempotency_key
            ON stock_ledger(idempotency_key)
            WHERE idempotency_key IS NOT NULL;
        """
    )
    return conn


def test_20pct_rounding_uses_largest_remainder_and_stable_tie_break() -> None:
    rows = [
        AnchorStockRow("SKU_A", "SKU_A_M", "M", 1),
        AnchorStockRow("SKU_B", "SKU_B_M", "M", 2),
        AnchorStockRow("SKU_C", "SKU_C_M", "M", 3),
        AnchorStockRow("SKU_D", "SKU_D_M", "M", 4),
    ]

    plan = compute_adjustment_plan(rows)

    assert plan.target_reduction_units == 2
    assert plan.generated_reduction_units == 2
    assert {row.sku_id: row.reduction_qty for row in plan.rows} == {
        "SKU_A_M": 0,
        "SKU_B_M": 0,
        "SKU_C_M": 1,
        "SKU_D_M": 1,
    }


def test_adjustment_apply_is_idempotent_for_same_anchor_and_batch(tmp_path: Path) -> None:
    conn = _make_db(tmp_path / "app.db")
    rows = [
        AnchorStockRow("SKU_A", "SKU_A_M", "M", 10),
        AnchorStockRow("SKU_B", "SKU_B_M", "M", 5),
    ]
    plan = compute_adjustment_plan(rows)

    first = apply_anchor_and_adjustment_events(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_rows=rows,
        adjustment_plan=plan,
        source_path="/tmp/anchor.xlsx",
        source_sha256="abc",
        anchor_snapshot_date="2026-04-04",
        anchor_event_date="2026-04-03",
        adjustment_event_date="2026-04-04",
        approved_by="owner",
        approved_at="2026-05-03T13:53:47+05:00",
        dry_run_report_path="/tmp/report.json",
    )
    second = apply_anchor_and_adjustment_events(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_rows=rows,
        adjustment_plan=plan,
        source_path="/tmp/anchor.xlsx",
        source_sha256="abc",
        anchor_snapshot_date="2026-04-04",
        anchor_event_date="2026-04-03",
        adjustment_event_date="2026-04-04",
        approved_by="owner",
        approved_at="2026-05-03T13:53:47+05:00",
        dry_run_report_path="/tmp/report.json",
    )

    ledger_count = conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0]
    batch_count = conn.execute("SELECT COUNT(*) FROM stock_adjustment_batch").fetchone()[0]

    assert first.already_applied is False
    assert second.already_applied is True
    assert ledger_count == len(rows) + len([row for row in plan.rows if row.reduction_qty > 0])
    assert batch_count == 1


def test_no_negative_snapshot_clamps_and_reports_raw_negative(tmp_path: Path) -> None:
    conn = _make_db(tmp_path / "app.db")
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, qty_change,
            reference_id, reference_type
        )
        VALUES ('2026-04-05', 'SALE', 'SKU_A', 'SKU_A_M', 'M', -5, 'ORDER1', 'SALE')
        """
    )
    rows = [AnchorStockRow("SKU_A", "SKU_A_M", "M", 3)]
    plan = compute_adjustment_plan(rows)
    apply_anchor_and_adjustment_events(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_rows=rows,
        adjustment_plan=plan,
        source_path="/tmp/anchor.xlsx",
        source_sha256="abc",
        anchor_snapshot_date="2026-04-04",
        anchor_event_date="2026-04-03",
        adjustment_event_date="2026-04-04",
        approved_by="owner",
        approved_at="2026-05-03T13:53:47+05:00",
        dry_run_report_path="/tmp/report.json",
    )

    snapshot = build_anchor_lineage_snapshot(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_date="2026-04-04",
        snapshot_date="2026-04-06",
    )

    assert snapshot.rows[0].current_stock == 0
    assert snapshot.rows[0].raw_current_stock == -3
    assert snapshot.negative_rows[0].sku_id == "SKU_A_M"


def test_ledger_to_snapshot_preserves_anchor_date_and_applies_after_anchor(tmp_path: Path) -> None:
    conn = _make_db(tmp_path / "app.db")
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, qty_change,
            reference_id, reference_type
        )
        VALUES ('2026-03-01', 'SALE', 'SKU_A', 'SKU_A_M', 'M', -100, 'OLD', 'SALE')
        """
    )
    rows = [AnchorStockRow("SKU_A", "SKU_A_M", "M", 10)]
    plan = compute_adjustment_plan(rows)
    apply_anchor_and_adjustment_events(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_rows=rows,
        adjustment_plan=plan,
        source_path="/tmp/anchor.xlsx",
        source_sha256="abc",
        anchor_snapshot_date="2026-04-04",
        anchor_event_date="2026-04-03",
        adjustment_event_date="2026-04-04",
        approved_by="owner",
        approved_at="2026-05-03T13:53:47+05:00",
        dry_run_report_path="/tmp/report.json",
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, qty_change,
            reference_id, reference_type
        )
        VALUES ('2026-04-05', 'SALE', 'SKU_A', 'SKU_A_M', 'M', -1, 'ORDER1', 'SALE')
        """
    )

    anchor_day = build_anchor_lineage_snapshot(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_date="2026-04-04",
        snapshot_date="2026-04-04",
    )
    after_anchor = build_anchor_lineage_snapshot(
        conn,
        anchor_id="ANCHOR1",
        batch_id="BATCH1",
        anchor_date="2026-04-04",
        snapshot_date="2026-04-06",
    )

    assert anchor_day.rows[0].current_stock == 10
    assert after_anchor.rows[0].current_stock == 7


def test_high_risk_family_exceptions_zero_active_without_double_reducing_overrides() -> None:
    rows = [
        AnchorStockRow("CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_4XL", "4XL", 56),
        AnchorStockRow("CL_NEW-CLO_MEN_T-SHIRT_BLACK", "CL_NEW-CLO_MEN_T-SHIRT_BLACK_M", "M", 34),
        AnchorStockRow("CL_OC_MEN_LINE51_WHITE", "CL_OC_MEN_LINE51_WHITE_M", "M", 100),
        AnchorStockRow("CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL", "4XL", 27),
    ]

    plan = compute_adjustment_plan(rows)
    exceptions = build_high_risk_exception_specs(rows, negative_rows=[])
    availability = build_offer_availability_rows(
        [
            ("CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_4XL", "4XL", 45),
            ("CL_NEW-CLO_MEN_T-SHIRT_BLACK", "CL_NEW-CLO_MEN_T-SHIRT_BLACK_M", "M", 27),
            ("CL_OC_MEN_LINE51_WHITE", "CL_OC_MEN_LINE51_WHITE_M", "M", 100),
            ("CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL", "4XL", 27),
        ],
        exceptions,
        snapshot_date="2026-05-03",
        source_manifest_id="source1",
    )

    reductions = {row.sku_id: row.reduction_qty for row in plan.rows}
    statuses = {row.sku_id: row.status for row in availability}
    offer_qty = {row.sku_id: row.offer_available_qty for row in availability}

    assert reductions["CL_OC_MEN_LINE51_WHITE_M"] == 0
    assert reductions["CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL"] == 0
    assert any(exc.reason_code == "OWNER_OOS_ACTIVE_ZERO" for exc in exceptions)
    assert any(exc.reason_code == "OWNER_OVERRIDE_NO_DOUBLE_REDUCE" for exc in exceptions)
    assert statuses["CL_OC_MEN_LINE52_BLACK_4XL"] == "OWNER_OOS_EXCEPTION"
    assert statuses["CL_NEW-CLO_MEN_T-SHIRT_BLACK_M"] == "OWNER_OOS_EXCEPTION"
    assert statuses["CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL"] == "OWNER_OVERRIDE_EXCLUDED"
    assert offer_qty["CL_OC_MEN_LINE52_BLACK_4XL"] == 0
    assert offer_qty["CL_NEW-CLO_MEN_T-SHIRT_BLACK_M"] == 0
    assert offer_qty["CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL"] == 0
    assert BASELINE_REFERENCE_TYPE == "BASELINE_20PCT_DECREASE"
    assert STOCK_ANCHOR_REFERENCE_TYPE == "STOCK_ANCHOR"
