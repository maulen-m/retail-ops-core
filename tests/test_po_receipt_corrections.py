import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import scripts.apply_line31_po_arc1_shortage_correction as apply_script
import scripts.generate_po_dashboard_data as dashboard
import scripts.report_line31_po_arc1_truth as report_script
from core.po.receipt_corrections import (
    CORRECTION_DECISION_TYPE,
    LINE31_PO_ARC1_CORRECTION_KEY,
    LINE31_PO_ARC1_DECISION_DATE,
    LINE31_PO_ARC1_STORE_CODE,
    build_line31_po_arc1_input_snapshot,
    build_line31_po_arc1_payload,
    get_receipt_correction,
)


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE audit_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_date TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            store_code TEXT,
            sku_key TEXT,
            input_snapshot TEXT,
            output_snapshot TEXT,
            human_action TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT,
            status TEXT,
            message_date TEXT,
            ship_date_seller TEXT,
            ship_date_cargo TEXT,
            alm_arrival_nom TEXT,
            ast_arrival_nom TEXT,
            alm_arrival_real TEXT,
            ast_arrival_real TEXT,
            units_total INTEGER,
            units_received INTEGER,
            weight_nom_kg REAL,
            weight_real_kg REAL,
            total_places INTEGER,
            total_cost_cny REAL,
            total_cost_kzt_supplier REAL,
            total_landed_cost_kzt REAL,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            supplier_id TEXT,
            message_date TEXT,
            cargo_send_date TEXT,
            estimated_arrival_date TEXT,
            actual_arrival_date TEXT,
            status TEXT,
            total_units INTEGER,
            est_weight_kg REAL,
            total_bags INTEGER
        );
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER,
            status TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO po_header (
            po_id, supplier_code, status, message_date, ship_date_cargo,
            ast_arrival_nom, ast_arrival_real, units_total, units_received,
            weight_nom_kg, total_places, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("PO_ARC-1", "ARC", "RECEIVED", "2026-02-06", "2026-02-07", "2026-02-28", "2026-03-02", 265, 0, 172.25, 4),
    )
    conn.execute(
        """
        INSERT INTO po_part (
            po_part_id, po_id, supplier_id, message_date, cargo_send_date,
            estimated_arrival_date, actual_arrival_date, status, total_units, est_weight_kg, total_bags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("ARC-1.0", "PO_ARC-1", "ARC", "2026-02-06", "2026-02-07", "2026-02-28", "2026-03-02", "RECEIVED", 265, 172.25, 4),
    )
    conn.executemany(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "PO_ARC-1",
                "ARC-1.0",
                "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK",
                "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M",
                "M",
                120,
                120,
                "RECEIVED",
            ),
            (
                "PO_ARC-1",
                "ARC-1.0",
                "CL_OF_ARC_WM_LINE31_C-025_WHALE-BLUE",
                "CL_OF_ARC_WM_LINE31_C-025_WHALE-BLUE_L",
                "L",
                145,
                145,
                "RECEIVED",
            ),
        ],
    )
    payload = build_line31_po_arc1_payload()
    input_snapshot = build_line31_po_arc1_input_snapshot(
        raw_po_line_units_total_sets=265,
        raw_po_line_units_received_sets=265,
        po_line_row_count=36,
    )
    conn.execute(
        """
        INSERT INTO audit_decisions (
            decision_date, decision_type, store_code, sku_key,
            input_snapshot, output_snapshot, human_action
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            LINE31_PO_ARC1_DECISION_DATE,
            CORRECTION_DECISION_TYPE,
            LINE31_PO_ARC1_STORE_CODE,
            LINE31_PO_ARC1_CORRECTION_KEY,
            json.dumps(input_snapshot, sort_keys=True),
            json.dumps(payload, sort_keys=True),
            "APPROVED",
        ),
    )
    conn.commit()
    conn.close()


def _seed_apply_db(
    db_path: Path,
    *,
    po_line_row_count: int,
    total_sets: int,
    received_sets: int,
    include_correction: bool = False,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE audit_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_date TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            store_code TEXT,
            sku_key TEXT,
            input_snapshot TEXT,
            output_snapshot TEXT,
            human_action TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER,
            status TEXT
        );
        CREATE TABLE sales_fact_v2 (
            order_date TEXT,
            sku_key TEXT,
            quantity INTEGER,
            status TEXT
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_key TEXT,
            event_type TEXT,
            qty_change INTEGER,
            event_date TEXT
        );
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock INTEGER,
            inbound_stock INTEGER
        );
        """
    )

    if po_line_row_count > 0:
        if po_line_row_count == 36 and total_sets == 265:
            quantities = [7] * 35 + [20]
        else:
            base = total_sets // po_line_row_count
            remainder = total_sets % po_line_row_count
            quantities = [base + (1 if idx < remainder else 0) for idx in range(po_line_row_count)]

        remaining_received = received_sets
        rows = []
        for idx, qty in enumerate(quantities):
            received_qty = min(qty, remaining_received)
            remaining_received -= received_qty
            rows.append(
                (
                    "PO_ARC-1",
                    "ARC-1.0",
                    f"CL_OF_ARC_WM_LINE31_FIXTURE_{idx:02d}",
                    f"CL_OF_ARC_WM_LINE31_FIXTURE_{idx:02d}_M",
                    "M",
                    qty,
                    received_qty,
                    "RECEIVED",
                )
            )
        conn.executemany(
            """
            INSERT INTO po_line (po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    conn.execute(
        """
        INSERT INTO sales_fact_v2 (order_date, sku_key, quantity, status)
        VALUES ('2026-04-15', 'CL_OF_ARC_WM_LINE31_FIXTURE_00', 5, 'SHIPPED')
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (sku_key, event_type, qty_change, event_date)
        VALUES ('CL_OF_ARC_WM_LINE31_FIXTURE_00', 'ADJUSTMENT', 5, '2026-04-10')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock, inbound_stock)
        VALUES ('2026-04-15', 'CL_OF_ARC_WM_LINE31_FIXTURE_00', 0, 0)
        """
    )

    if include_correction:
        payload = build_line31_po_arc1_payload()
        input_snapshot = build_line31_po_arc1_input_snapshot(
            raw_po_line_units_total_sets=total_sets,
            raw_po_line_units_received_sets=received_sets,
            po_line_row_count=po_line_row_count,
        )
        conn.execute(
            """
            INSERT INTO audit_decisions (
                decision_date, decision_type, store_code, sku_key,
                input_snapshot, output_snapshot, human_action
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LINE31_PO_ARC1_DECISION_DATE,
                CORRECTION_DECISION_TYPE,
                LINE31_PO_ARC1_STORE_CODE,
                LINE31_PO_ARC1_CORRECTION_KEY,
                json.dumps(input_snapshot, sort_keys=True),
                json.dumps(payload, sort_keys=True),
                "APPROVED",
            ),
        )

    conn.commit()
    conn.close()


def test_get_receipt_correction_loads_line31_po_arc1_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        correction = get_receipt_correction(conn, "PO_ARC-1")

    assert correction is not None
    assert correction["payload"]["received_pieces"] == 638
    assert correction["payload"]["net_shortage_pieces"] == 157
    assert correction["payload"]["compensation_claim_pieces"] == 177
    assert correction["input_snapshot"]["raw_po_line_units_received_sets"] == 265


def test_load_po_orders_attaches_receipt_correction_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    po = dashboard.load_po_orders("PO_ARC-1", db_path=db_path)

    assert po is not None
    assert po["receipt_correction_applied"] is True
    assert po["receipt_correction_po_id"] == "PO_ARC-1"
    assert po["receipt_correction_basis"] == "PIECES"
    assert po["receipt_received_pieces"] == 638
    assert po["receipt_net_shortage_pieces"] == 157
    assert po["receipt_compensation_claim_pieces"] == 177
    assert po["receipt_raw_po_line_units_received_sets"] == 265


def test_load_real_pos_part_row_keeps_parent_correction_visible(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    rows = dashboard.load_real_pos(db_path=db_path)
    row = next(item for item in rows if item["po_id"] == "ARC-1.0")

    assert row["parent_po_id"] == "PO_ARC-1"
    assert row["receipt_correction_applied"] is True
    assert row["receipt_correction_po_id"] == "PO_ARC-1"
    assert row["receipt_ordered_pieces"] == 795
    assert row["receipt_received_pieces"] == 638
    assert row["receipt_compensation_claim_by_model"] == {"MTW01": 64, "JYM005": 53, "MT20": 60}


def test_apply_correction_fails_closed_when_po_arc1_has_zero_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_apply_db(
        db_path,
        po_line_row_count=0,
        total_sets=0,
        received_sets=0,
    )

    with pytest.raises(RuntimeError, match="zero po_line rows"):
        apply_script.apply_correction(
            db_path=db_path,
            backup_root=tmp_path / "backups",
            report_path=tmp_path / "report.md",
            apply=False,
        )


def test_apply_correction_fails_closed_when_baseline_is_unexpected(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_apply_db(
        db_path,
        po_line_row_count=36,
        total_sets=265,
        received_sets=264,
    )

    with pytest.raises(RuntimeError, match="Unexpected PO-ARC-1 raw baseline"):
        apply_script.apply_correction(
            db_path=db_path,
            backup_root=tmp_path / "backups",
            report_path=tmp_path / "report.md",
            apply=False,
        )


def test_report_as_of_controls_report_date_and_default_output_path(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_apply_db(
        db_path,
        po_line_row_count=36,
        total_sets=265,
        received_sets=265,
        include_correction=True,
    )

    as_of_date = date.fromisoformat("2026-04-24")
    report = report_script.build_truth_report(db_path, as_of_date=as_of_date)
    output_dir = report_script.resolve_output_dir(None, as_of_date=as_of_date)
    paths = report_script.write_report(report, output_dir)

    assert report["as_of_date"] == "2026-04-24"
    assert output_dir == report_script.DEFAULT_OUTPUT_ROOT / "2026-04-24"
    assert paths["md_path"].endswith("/2026-04-24/line31_po_arc1_truth_report.md")
