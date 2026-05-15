from __future__ import annotations

import json
import sqlite3
from typing import Any


CORRECTION_DECISION_TYPE = "PO_RECEIPT_CORRECTION"
LINE31_PO_ARC1_DECISION_DATE = "2026-04-13"
LINE31_PO_ARC1_STORE_CODE = "ACMEWEAR"
LINE31_PO_ARC1_CORRECTION_KEY = "PO_ARC-1/LINE31"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _parse_json(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def build_line31_po_arc1_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "po_id": "PO_ARC-1",
        "family": "LINE31",
        "store_code": LINE31_PO_ARC1_STORE_CODE,
        "unit_basis": "PIECES",
        "ordered_pieces": 795,
        "ordered_sets_raw": 265,
        "pieces_per_set": 3,
        "received_pieces": 638,
        "net_shortage_pieces": 157,
        "compensation_claim_pieces": 177,
        "compensation_claim_by_model": {
            "MTW01": 64,
            "JYM005": 53,
            "MT20": 60,
        },
        "compensation_value_cny": 3008.50,
        "shipment_date": "2026-02-07",
        "receipt_date": "2026-03-02",
        "final_count_date": "2026-04-10",
        "compensation_request_date": "2026-04-13",
        "route_separation_note": (
            "Old Li Sijia / PO-1 recovery route remains separate from the current Tracy / Wuchun route."
        ),
        "assumption_warning": (
            "Do not interpret the 177-piece compensation claim as sets, and do not import Sourcing current stock "
            "from this historical shortage packet."
        ),
        "source_evidence_paths": [
            "~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/"
            "LINE31_INITIAL_PO_SHORTAGE_AUTONOMOUS_BUSINESS_CONTEXT__2026-04-24.md",
            "~/Cowork/Projects/Sourcing-Research/docs/inventory/products/LINE31_sales__LINE31_Shortage.md",
            "~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/13.4.26/"
            "shortage_compensation/PO_LINE31_13.4.2026_shortage_compensation_messages_ARC-1.md",
        ],
        "confidence": "owner_handoff_confirmed",
    }


def build_line31_po_arc1_input_snapshot(
    *,
    raw_po_line_units_total_sets: int = 265,
    raw_po_line_units_received_sets: int = 265,
    po_line_row_count: int = 36,
) -> dict[str, Any]:
    return {
        "po_line_grain": "set_sku_lines",
        "raw_po_line_units_total_sets": int(raw_po_line_units_total_sets),
        "raw_po_line_units_received_sets": int(raw_po_line_units_received_sets),
        "po_line_row_count": int(po_line_row_count),
        "note": (
            "Raw po_line quantities remain at set-line grain; the correction payload carries the authoritative "
            "piece-basis shortage and compensation claim."
        ),
    }


def get_receipt_corrections_by_po(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not _table_exists(conn, "audit_decisions"):
        return {}

    rows = conn.execute(
        """
        SELECT
            id,
            decision_date,
            store_code,
            sku_key,
            input_snapshot,
            output_snapshot,
            human_action,
            created_at
        FROM audit_decisions
        WHERE decision_type = ?
        ORDER BY created_at DESC, id DESC
        """,
        (CORRECTION_DECISION_TYPE,),
    ).fetchall()

    corrections: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = _parse_json(row["output_snapshot"])
        po_id = str(payload.get("po_id") or "").strip()
        if not po_id or po_id in corrections:
            continue
        corrections[po_id] = {
            "decision_date": row["decision_date"],
            "store_code": row["store_code"],
            "correction_key": row["sku_key"],
            "input_snapshot": _parse_json(row["input_snapshot"]),
            "payload": payload,
            "human_action": row["human_action"],
            "created_at": row["created_at"],
        }

    return corrections


def get_receipt_correction(conn: sqlite3.Connection, po_id: str) -> dict[str, Any] | None:
    return get_receipt_corrections_by_po(conn).get(str(po_id or "").strip())


def annotate_po_payload(
    payload: dict[str, Any],
    correction: dict[str, Any] | None,
) -> dict[str, Any]:
    annotated = dict(payload)
    if not correction:
        annotated.setdefault("receipt_correction_applied", False)
        return annotated

    correction_payload = dict(correction.get("payload") or {})
    input_snapshot = dict(correction.get("input_snapshot") or {})
    annotated.update(
        {
            "receipt_correction_applied": True,
            "receipt_correction_decision_type": CORRECTION_DECISION_TYPE,
            "receipt_correction_decision_date": correction.get("decision_date"),
            "receipt_correction_human_action": correction.get("human_action"),
            "receipt_correction_created_at": correction.get("created_at"),
            "receipt_correction_store_code": correction.get("store_code"),
            "receipt_correction_key": correction.get("correction_key"),
            "receipt_correction_po_id": correction_payload.get("po_id"),
            "receipt_correction_family": correction_payload.get("family"),
            "receipt_correction_basis": correction_payload.get("unit_basis"),
            "receipt_ordered_pieces": correction_payload.get("ordered_pieces"),
            "receipt_received_pieces": correction_payload.get("received_pieces"),
            "receipt_net_shortage_pieces": correction_payload.get("net_shortage_pieces"),
            "receipt_compensation_claim_pieces": correction_payload.get("compensation_claim_pieces"),
            "receipt_compensation_claim_by_model": correction_payload.get("compensation_claim_by_model") or {},
            "receipt_compensation_value_cny": correction_payload.get("compensation_value_cny"),
            "receipt_shipment_date": correction_payload.get("shipment_date"),
            "receipt_date": correction_payload.get("receipt_date"),
            "receipt_final_count_date": correction_payload.get("final_count_date"),
            "receipt_compensation_request_date": correction_payload.get("compensation_request_date"),
            "receipt_route_separation_note": correction_payload.get("route_separation_note"),
            "receipt_assumption_warning": correction_payload.get("assumption_warning"),
            "receipt_correction_confidence": correction_payload.get("confidence"),
            "receipt_correction_source_paths": correction_payload.get("source_evidence_paths") or [],
            "receipt_raw_po_line_units_total_sets": input_snapshot.get("raw_po_line_units_total_sets"),
            "receipt_raw_po_line_units_received_sets": input_snapshot.get("raw_po_line_units_received_sets"),
            "receipt_raw_po_line_row_count": input_snapshot.get("po_line_row_count"),
            "receipt_assumption_status": "PIECE_CORRECTION_ACTIVE__RAW_SET_RECEIPT_NOT_CANONICAL",
        }
    )
    return annotated
