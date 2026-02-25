from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.validate_schema import validate_schema


def _seed_min_schema(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_header (
            po_id TEXT,
            supplier_code TEXT,
            status TEXT,
            message_date TEXT,
            ship_date_seller TEXT,
            ship_date_cargo TEXT,
            alm_arrival_nom TEXT,
            ast_arrival_nom TEXT,
            units_total INTEGER,
            units_received INTEGER,
            weight_nom_kg REAL,
            total_places INTEGER
        );
        CREATE TABLE po_part (
            po_part_id TEXT,
            po_id TEXT,
            status TEXT,
            est_weight_kg REAL,
            total_bags INTEGER,
            total_units INTEGER,
            is_paid_base INTEGER,
            is_paid_dlv INTEGER,
            to_pay_base_kzt REAL,
            to_pay_dlv_kzt REAL
        );
        CREATE TABLE fact_po_draft (
            draft_id TEXT, status TEXT, supplier_code TEXT, total_units INTEGER,
            total_cost_cny REAL, total_cost_kzt REAL, total_po_value_kzt REAL,
            total_order_qty INTEGER, skus_count INTEGER, roic_action_summary TEXT,
            guardrail_status TEXT, notes TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE fact_po_draft_lines (
            line_id TEXT, draft_id TEXT, sku_key TEXT, sku_id TEXT, my_size TEXT,
            quantity INTEGER, unit_cost_cny REAL, roic_pct REAL
        );
        CREATE TABLE fact_po_approvals (
            approval_id TEXT, draft_id TEXT, sku_key TEXT, roic_action TEXT,
            approved_by TEXT, approved_at TEXT, decision TEXT, notes TEXT,
            po_value_kzt REAL, order_qty INTEGER
        );
        CREATE TABLE fact_po_execution (
            execution_id TEXT, draft_id TEXT, po_id TEXT, approval_id TEXT,
            planned_units INTEGER, executed_lines INTEGER, total_value_kzt REAL,
            notes TEXT, executed_by TEXT, executed_at TEXT, status TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_validate_schema_passes_for_required_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "ok.db"
    _seed_min_schema(db_path)
    assert validate_schema(db_path) == []


def test_validate_schema_fails_for_missing_required_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "broken.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_header (po_id TEXT);
        CREATE TABLE po_part (po_part_id TEXT);
        CREATE TABLE fact_po_draft (draft_id TEXT);
        CREATE TABLE fact_po_draft_lines (line_id TEXT);
        CREATE TABLE fact_po_approvals (approval_id TEXT);
        CREATE TABLE fact_po_execution (execution_id TEXT);
        """
    )
    conn.commit()
    conn.close()

    errors = validate_schema(db_path)
    assert errors
    text = "\n".join(errors)
    assert "po_part missing columns" in text
    assert "po_header missing columns" in text
