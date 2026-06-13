from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.materialize_governed_stock_repairs import (
    ENV_GATE,
    build_governed_stock_repair_plan,
    materialize_governed_stock_repairs,
)


def _create_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
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
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            idempotency_key TEXT
        );
        CREATE UNIQUE INDEX ux_stock_ledger_idempotency_key
        ON stock_ledger(idempotency_key)
        WHERE idempotency_key IS NOT NULL;
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT NOT NULL,
            actual_arrival_date TEXT,
            status TEXT
        );
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY,
            po_id TEXT NOT NULL,
            po_part_id TEXT,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING'
        );
        """
    )
    return conn


def _write_manual_count(path: Path) -> None:
    fields = [
        "stock_pool_id",
        "quantity",
        "status",
        "batch_id",
        "count_timestamp_at_almaty",
    ]
    rows = [
        {
            "stock_pool_id": "CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_L",
            "quantity": "105",
            "status": "OWNER_APPROVED",
            "batch_id": "COUNT",
            "count_timestamp_at_almaty": "2026-06-04T14:00:23+05:00",
        }
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(path: Path, manual_csv: Path) -> None:
    manifest = {
        "schema_version": "governed_stock_repair_events.v1",
        "run_id": "pytest_governed_stock_repair",
        "repairs": [
            {
                "repair_id": "nike_alias",
                "repair_type": "manual_count_size_alias_delta",
                "sku_key": "CL_NEW-CLO_MEN_NIKE-SHIRT_GREY",
                "sku_id": "CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46",
                "my_size": "46",
                "store_code": "UNIVERSAL",
                "qty_change": 5,
                "expected_current_balance": -5,
                "event_date": "2026-06-04",
                "event_type": "ADJUSTMENT",
                "reference_type": "MANUAL_COUNT_SIZE_ALIAS",
                "reference_id": "COUNT:L->46",
                "source_artifact_path": str(manual_csv),
                "source_stock_pool_id": "CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_L",
                "source_min_quantity": 105,
                "source_status": "OWNER_APPROVED",
            },
            {
                "repair_id": "line31_po_line",
                "repair_type": "po_line_received_delta",
                "sku_key": "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK",
                "sku_id": "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M",
                "my_size": "M",
                "store_code": "UNIVERSAL",
                "qty_change": 4,
                "expected_current_balance": -4,
                "event_date": "2026-03-02",
                "event_type": "INBOUND",
                "reference_type": "PO_INBOUND_LINE",
                "reference_id": "907",
                "source_po_line_id": 907,
                "source_po_part_id": "ARC-1.0",
                "source_min_received_qty": 10,
            },
        ],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_governed_stock_repair_is_dry_run_and_apply_gated(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_db(db_path)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_type, reference_id
        ) VALUES ('2026-06-13', 'SALE', 'CL_NEW-CLO_MEN_NIKE-SHIRT_GREY',
                  'CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46', '46', 'UNIVERSAL',
                  -5, 'SALE', 'ORDER-1')
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_type, reference_id
        ) VALUES ('2026-06-13', 'SALE', 'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK',
                  'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M', 'M', 'UNIVERSAL',
                  -4, 'SALE', 'ORDER-2')
        """
    )
    conn.execute(
        "INSERT INTO po_part (po_part_id, po_id, actual_arrival_date, status) VALUES ('ARC-1.0', 'PO_ARC-1', '2026-03-02', 'RECEIVED')"
    )
    conn.execute(
        """
        INSERT INTO po_line (
            po_line_id, po_id, po_part_id, sku_key, sku_id, my_size,
            order_qty, received_qty, status
        ) VALUES (907, 'PO_ARC-1', 'ARC-1.0', 'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK',
                  'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M', 'M', 10, 10, 'RECEIVED')
        """
    )
    conn.commit()
    conn.close()

    manual_csv = tmp_path / "manual.csv"
    manifest = tmp_path / "manifest.json"
    _write_manual_count(manual_csv)
    _write_manifest(manifest, manual_csv)

    dry = materialize_governed_stock_repairs(
        db_path=db_path,
        manifest_path=manifest,
        output_root=tmp_path / "dry",
        apply=False,
    )
    assert dry["summary"]["candidate_event_count"] == 2
    assert dry["summary"]["blocked_count"] == 0
    assert dry["summary"]["applied_rows"] == 0

    blocked = materialize_governed_stock_repairs(
        db_path=db_path,
        manifest_path=manifest,
        output_root=tmp_path / "blocked",
        apply=False,
    )
    assert blocked["summary"]["candidate_event_count"] == 2

    monkeypatch.setenv(ENV_GATE, "1")
    applied = materialize_governed_stock_repairs(
        db_path=db_path,
        manifest_path=manifest,
        output_root=tmp_path / "apply",
        apply=True,
    )
    assert applied["summary"]["applied_rows"] == 2

    conn = sqlite3.connect(str(db_path))
    balances = dict(
        conn.execute(
            """
            SELECT sku_id, SUM(qty_change)
            FROM stock_ledger
            GROUP BY sku_id
            """
        ).fetchall()
    )
    assert balances["CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46"] == 0
    assert balances["CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M"] == 0


def test_governed_stock_repair_blocks_when_balance_drifted(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_db(db_path)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_type, reference_id
        ) VALUES ('2026-06-13', 'SALE', 'CL_NEW-CLO_MEN_NIKE-SHIRT_GREY',
                  'CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46', '46', 'UNIVERSAL',
                  -4, 'SALE', 'ORDER-1')
        """
    )
    conn.commit()
    manual_csv = tmp_path / "manual.csv"
    manifest = tmp_path / "manifest.json"
    _write_manual_count(manual_csv)
    _write_manifest(manifest, manual_csv)

    plan = build_governed_stock_repair_plan(conn, manifest_path=manifest)

    assert plan.summary["blocked_count"] == 2
    assert any("CURRENT_BALANCE_MISMATCH" in row["errors"] for row in plan.blocked_rows)
