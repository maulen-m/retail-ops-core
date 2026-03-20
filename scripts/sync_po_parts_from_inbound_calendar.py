#!/usr/bin/env python3
"""
Sync split-PO inbound calendar workbook into po_header/po_part/po_line.

Default: DRY RUN.
Apply requires ENABLE_PO_PART_SYNC_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, date
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.excel.dim_sku_light_parser import parse_dim_sku_light

DEFAULT_XLSX = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/"
    "Purchase_orders/vibe_code_PO/backup/7.2.26/Inbound_calendar_V10.002.xlsx"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"

REQUIRED_INBOUNDS_COLS = [
    "SKU Key",
    "Size",
    "message_date",
    "Order Qty_Approved",
    "PO_id",
    "PO_part_id",
    "cargo_send_date",
    "Estimated_Arrival_date",
    "Actual_Arrival_date",
    "Status",
    "base_cost",
    "PO Base (CNY)",
    "Actual_qty",
    "supplier_id",
]

REQUIRED_PART_COLS = [
    "PO_part_id",
    "PO_id",
    "supplier_id",
    "Cargo_freight_id",
    "message_date",
    "cargo_send_date",
    "Estimated_Arrival_date",
    "Actual_Arrival_date",
    "Actual_DLV_PAY_date",
    "Status",
    "Total Units",
    "Base_cost_CNY",
    "Actual_Weight_kg",
    "Paid_DLV_USD",
    "Paid_DLV_KZT",
    "Final_USD_per_kg",
    "USD_KZT_rate",
    "Actual_DLV_days",
]


def _normalize_size(raw: Any) -> str:
    if raw is None:
        return ""
    txt = str(raw).strip().upper()
    if not txt or txt == "NAN":
        return ""
    return txt.replace(" ", "_")


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    # Excel serial date support (e.g., 46035 -> 2026-01-13)
    if isinstance(value, (int, float)):
        try:
            serial = float(value)
            if serial > 0:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")).date().isoformat()
        except Exception:
            pass
    raw = str(value).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        try:
            serial = float(raw)
            if serial > 0:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")).date().isoformat()
        except Exception:
            pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_int(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_paid_flag(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    txt = str(value).strip().upper()
    if txt in {"YES", "Y", "TRUE", "PAID", "1"}:
        return 1
    if txt in {"NO", "N", "FALSE", "UNPAID", "0", ""}:
        return 0
    try:
        return 1 if float(txt) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _ensure_columns(df: pd.DataFrame, required: list[str], sheet: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise RuntimeError(f"{sheet} missing required columns: {', '.join(missing)}")


def _load_sku_price_map(xlsx_path: Path, sheet_name: str) -> dict[str, dict[str, float]]:
    parsed, _ = parse_dim_sku_light(
        xlsx_path,
        sheet_name=sheet_name,
    )
    out: dict[str, dict[str, float]] = {}
    for sku_key, row in parsed.items():
        out[sku_key] = {
            "avg_price": float(row.get("avg_price_kzt") or 0.0),
            "weight_kg": float(row.get("weight_kg") or 1.0),
            "base_cost_cny": float(row.get("base_cost_cny") or 0.0),
        }
    return out


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _map_part_status(raw: Any) -> str:
    txt = str(raw or "").strip().lower()
    if txt in {"arrived", "received", "done"}:
        return "RECEIVED"
    if txt in {"transit", "in_transit", "in transit", "shipped", "shipped_cargo"}:
        return "IN_TRANSIT"
    if txt in {"draft", ""}:
        return "DRAFT"
    return txt.upper()


def _is_summary_marker(raw: Any) -> bool:
    txt = str(raw or "").strip().upper()
    if not txt:
        return True
    if txt in {"NAN", "NONE", "NULL"}:
        return True
    bad_tokens = ("TOTAL", "PENDING", "UNPAID", "PAYMENT")
    return any(token in txt for token in bad_tokens)


def _is_valid_po_id(raw: Any) -> bool:
    txt = str(raw or "").strip()
    if _is_summary_marker(txt):
        return False
    upper = txt.upper()
    return bool(re.match(r"^(PO[-_].+|.+_PO-\d+)$", upper))


def _is_valid_po_part_id(raw: Any) -> bool:
    txt = str(raw or "").strip()
    if _is_summary_marker(txt):
        return False
    upper = txt.upper()
    return bool(re.match(r"^(PO[-_].+|ARC[-_].+|.+_PO-\d+)$", upper))


def _cleanup_invalid_parts(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "po_part"):
        return
    invalid = []
    for row in conn.execute("SELECT po_part_id FROM po_part").fetchall():
        po_part_id = str(row[0] or "").strip()
        if not _is_valid_po_part_id(po_part_id):
            invalid.append(po_part_id)
    for po_part_id in invalid:
        conn.execute("DELETE FROM po_part WHERE po_part_id = ?", (po_part_id,))


def _cleanup_legacy_po_line_rows(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "po_line"):
        return
    conn.execute(
        """
        DELETE FROM po_line
        WHERE COALESCE(TRIM(po_part_id), '') = ''
          AND po_id IN (
            SELECT po_id
            FROM po_line
            GROUP BY po_id
            HAVING SUM(CASE WHEN COALESCE(TRIM(po_part_id), '') <> '' THEN 1 ELSE 0 END) > 0
          )
        """
    )


def _upsert_dim_sku(
    conn: sqlite3.Connection,
    sku_key: str,
    base_cost_cny: float,
    sku_price_map: dict[str, dict[str, float]],
    *,
    allow_weight_overwrite: bool = False,
) -> None:
    if not _table_exists(conn, "dim_sku"):
        return

    cols = _table_columns(conn, "dim_sku")
    sku_meta = sku_price_map.get(sku_key, {})
    model = sku_key.split("_")[-2] if "_" in sku_key else sku_key
    product_type = sku_key.split("_")[0] if "_" in sku_key else "CL"
    payload = {
        "sku_key": sku_key,
        "model": model,
        "product_type": product_type,
        "base_cost_cny": base_cost_cny if base_cost_cny > 0 else (sku_meta.get("base_cost_cny") or 1.0),
        "weight_kg": sku_meta.get("weight_kg") or 1.0,
        "avg_sell_price_kzt_used": sku_meta.get("avg_price"),
        "avg_sell_price_source": "INBOUND_CALENDAR_V10.002",
        "active_flag": 1,
    }
    usable = {k: v for k, v in payload.items() if k in cols}
    existing = conn.execute("SELECT 1 FROM dim_sku WHERE sku_key = ? LIMIT 1", (sku_key,)).fetchone()
    if existing:
        update_keys = [k for k in usable.keys() if k != "sku_key"]
        if not allow_weight_overwrite and "weight_kg" in update_keys:
            update_keys.remove("weight_kg")
        if not update_keys:
            return
        updates = ", ".join(f"{k} = ?" for k in update_keys)
        params = [usable[k] for k in update_keys] + [sku_key]
        conn.execute(f"UPDATE dim_sku SET {updates} WHERE sku_key = ?", params)
    else:
        fields = ", ".join(usable.keys())
        placeholders = ", ".join(["?"] * len(usable))
        conn.execute(
            f"INSERT INTO dim_sku ({fields}) VALUES ({placeholders})",
            [usable[k] for k in usable.keys()],
        )


def _upsert_dim_sku_size(conn: sqlite3.Connection, sku_id: str, sku_key: str, my_size: str) -> None:
    if not _table_exists(conn, "dim_sku_size"):
        return
    cols = _table_columns(conn, "dim_sku_size")
    payload = {
        "sku_id": sku_id,
        "sku_key": sku_key,
        "my_size": my_size,
        "active_flag": 1,
    }
    usable = {k: v for k, v in payload.items() if k in cols}
    existing = conn.execute("SELECT 1 FROM dim_sku_size WHERE sku_id = ? LIMIT 1", (sku_id,)).fetchone()
    if existing:
        updates = ", ".join(f"{k} = ?" for k in usable.keys() if k != "sku_id")
        params = [usable[k] for k in usable.keys() if k != "sku_id"] + [sku_id]
        conn.execute(f"UPDATE dim_sku_size SET {updates} WHERE sku_id = ?", params)
    else:
        fields = ", ".join(usable.keys())
        placeholders = ", ".join(["?"] * len(usable))
        conn.execute(
            f"INSERT INTO dim_sku_size ({fields}) VALUES ({placeholders})",
            [usable[k] for k in usable.keys()],
        )


def sync_po_parts_from_workbook(
    *,
    xlsx_path: Path,
    db_path: Path,
    sheet_inbounds: str = "Inbounds_sheet",
    sheet_parts: str = "PO_part_id_Totals",
    sheet_sku: str = "DIM_SKU_light_v5",
    apply: bool = False,
    allow_dim_sku_weight_overwrite: bool = False,
) -> dict[str, Any]:
    if apply and os.environ.get("ENABLE_PO_PART_SYNC_WRITE") != "1":
        raise RuntimeError("ENABLE_PO_PART_SYNC_WRITE=1 is required with --apply")

    inbounds_df = pd.read_excel(xlsx_path, sheet_name=sheet_inbounds, dtype=object)
    parts_df = pd.read_excel(xlsx_path, sheet_name=sheet_parts, dtype=object)
    _ensure_columns(inbounds_df, REQUIRED_INBOUNDS_COLS, sheet_inbounds)
    _ensure_columns(parts_df, REQUIRED_PART_COLS, sheet_parts)
    sku_price_map = _load_sku_price_map(xlsx_path, sheet_sku)

    valid_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for _, row in inbounds_df.iterrows():
        po_id = str(row.get("PO_id") or "").strip()
        po_part_id = str(row.get("PO_part_id") or "").strip()
        sku_key = str(row.get("SKU Key") or "").strip()
        my_size = _normalize_size(row.get("Size"))
        qty = _to_int(row.get("Order Qty_Approved"))
        if not _is_valid_po_id(po_id) or not _is_valid_po_part_id(po_part_id):
            warnings.append(
                f"skip invalid po identifiers po={po_id} part={po_part_id} sku={sku_key} size={my_size}"
            )
            continue
        if not po_id or not po_part_id or not sku_key or not my_size or qty <= 0:
            warnings.append(f"skip invalid row po={po_id} part={po_part_id} sku={sku_key} size={my_size} qty={qty}")
            continue
        valid_rows.append(
            {
                "po_id": po_id,
                "po_part_id": po_part_id,
                "supplier_id": str(row.get("supplier_id") or "").strip(),
                "sku_key": sku_key,
                "my_size": my_size,
                "sku_id": f"{sku_key}_{my_size}",
                "message_date": _parse_date(row.get("message_date")),
                "cargo_send_date": _parse_date(row.get("cargo_send_date")),
                "estimated_arrival_date": _parse_date(row.get("Estimated_Arrival_date")),
                "actual_arrival_date": _parse_date(row.get("Actual_Arrival_date")),
                "status": _map_part_status(row.get("Status")),
                "order_qty": qty,
                "received_qty": _to_int(row.get("Actual_qty")),
                "base_cost_cny": _to_float(row.get("base_cost")),
                "line_cost_cny": _to_float(row.get("PO Base (CNY)")) or qty * _to_float(row.get("base_cost")),
            }
        )

    po_ids = sorted({row["po_id"] for row in valid_rows})
    po_part_ids = sorted({row["po_part_id"] for row in valid_rows})
    summary: dict[str, Any] = {
        "apply": apply,
        "allow_dim_sku_weight_overwrite": allow_dim_sku_weight_overwrite,
        "rows_inbounds_total": int(len(inbounds_df)),
        "rows_inbounds_valid": len(valid_rows),
        "rows_parts_total": int(len(parts_df)),
        "po_ids": po_ids,
        "po_part_ids": po_part_ids,
        "warnings": warnings,
        "inserted": {"po_header": 0, "po_part": 0, "po_line": 0},
        "updated": {"po_header": 0, "po_part": 0, "po_line": 0},
    }
    if not apply:
        return summary

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        po_line_cols = _table_columns(conn, "po_line")
        if "po_part_id" not in po_line_cols:
            raise RuntimeError("po_line.po_part_id is missing; run migrate_023_po_parts_schema.py first")

        _cleanup_invalid_parts(conn)
        _cleanup_legacy_po_line_rows(conn)

        # Upsert po_part from totals sheet first
        part_cols = _table_columns(conn, "po_part")
        for _, row in parts_df.iterrows():
            po_part_id = str(row.get("PO_part_id") or "").strip()
            po_id = str(row.get("PO_id") or "").strip()
            if not _is_valid_po_id(po_id) or not _is_valid_po_part_id(po_part_id):
                continue
            if not po_part_id or not po_id:
                continue
            payload = {
                "po_part_id": po_part_id,
                "po_id": po_id,
                "supplier_id": str(row.get("supplier_id") or "").strip(),
                "cargo_freight_id": str(row.get("Cargo_freight_id") or "").strip(),
                "message_date": _parse_date(row.get("message_date")),
                "cargo_send_date": _parse_date(row.get("cargo_send_date")),
                "estimated_arrival_date": _parse_date(row.get("Estimated_Arrival_date")),
                "actual_arrival_date": _parse_date(row.get("Actual_Arrival_date")),
                "actual_dlv_pay_date": _parse_date(row.get("Actual_DLV_PAY_date")),
                "status": _map_part_status(row.get("Status")),
                "total_sku_keys": _to_int(row.get("Total SKU Keys")),
                "total_units": _to_int(row.get("Total Units")),
                "base_cost_cny": _to_float(row.get("Base_cost_CNY")),
                "base_cost_kzt": _to_float(row.get("Base_cost_KZT")),
                "est_weight_kg": _to_float(row.get("Est. Weight (kg)")),
                "est_delivery_usd": _to_float(row.get("Est. Delivery (USD)")),
                "total_bags": _to_int(row.get("Total Bags")),
                "qty_delta": _to_int(row.get("Qty Delta")),
                "est_delivery_kzt": _to_float(row.get("Est. Delivery (KZT)")),
                "actual_weight_kg": _to_float(row.get("Actual_Weight_kg")),
                "paid_dlv_usd": _to_float(row.get("Paid_DLV_USD")),
                "paid_dlv_kzt": _to_float(row.get("Paid_DLV_KZT")),
                "final_usd_per_kg": _to_float(row.get("Final_USD_per_kg")),
                "usd_kzt_rate": _to_float(row.get("USD_KZT_rate")),
                "actual_dlv_days": _to_int(row.get("Actual_DLV_days")),
                "is_paid_base": _to_paid_flag(row.get("is_paid_BASE")),
                "is_paid_dlv": _to_paid_flag(row.get("is_paid_DLV")),
                "to_pay_base_kzt": _to_float(row.get("To_pay_BASE_KZT")),
                "to_pay_dlv_kzt": _to_float(row.get("To_pay_DLV_KZT")),
            }
            usable = {k: v for k, v in payload.items() if k in part_cols}
            existing = conn.execute("SELECT 1 FROM po_part WHERE po_part_id = ? LIMIT 1", (po_part_id,)).fetchone()
            if existing:
                updates = ", ".join(f"{k} = ?" for k in usable.keys() if k != "po_part_id")
                params = [usable[k] for k in usable.keys() if k != "po_part_id"] + [po_part_id]
                conn.execute(f"UPDATE po_part SET {updates} WHERE po_part_id = ?", params)
                summary["updated"]["po_part"] += 1
            else:
                fields = ", ".join(usable.keys())
                placeholders = ", ".join(["?"] * len(usable))
                conn.execute(
                    f"INSERT INTO po_part ({fields}) VALUES ({placeholders})",
                    [usable[k] for k in usable.keys()],
                )
                summary["inserted"]["po_part"] += 1

        # Fallback upsert po_part if missing from totals sheet
        part_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in valid_rows:
            part_group[(row["po_id"], row["po_part_id"])].append(row)
        for (po_id, po_part_id), rows in part_group.items():
            existing = conn.execute("SELECT 1 FROM po_part WHERE po_part_id = ? LIMIT 1", (po_part_id,)).fetchone()
            if existing:
                continue
            total_units = sum(r["order_qty"] for r in rows)
            total_base = sum(r["line_cost_cny"] for r in rows)
            payload = {
                "po_part_id": po_part_id,
                "po_id": po_id,
                "supplier_id": rows[0]["supplier_id"],
                "message_date": rows[0]["message_date"],
                "cargo_send_date": rows[0]["cargo_send_date"],
                "estimated_arrival_date": rows[0]["estimated_arrival_date"],
                "actual_arrival_date": rows[0]["actual_arrival_date"],
                "status": rows[0]["status"],
                "total_units": total_units,
                "base_cost_cny": total_base,
            }
            usable = {k: v for k, v in payload.items() if k in part_cols}
            fields = ", ".join(usable.keys())
            placeholders = ", ".join(["?"] * len(usable))
            conn.execute(
                f"INSERT INTO po_part ({fields}) VALUES ({placeholders})",
                [usable[k] for k in usable.keys()],
            )
            summary["inserted"]["po_part"] += 1

        # Upsert po_header aggregated from valid rows
        header_cols = _table_columns(conn, "po_header")
        po_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in valid_rows:
            po_group[row["po_id"]].append(row)

        def _po_status(rows: list[dict[str, Any]]) -> str:
            statuses = {r["status"] for r in rows}
            if "IN_TRANSIT" in statuses:
                return "IN_TRANSIT"
            if statuses == {"RECEIVED"}:
                return "RECEIVED"
            return "DRAFT"

        for po_id, rows in po_group.items():
            part_agg = conn.execute(
                """
                SELECT
                    SUM(COALESCE(total_units, 0)) AS total_units,
                    SUM(COALESCE(base_cost_cny, 0)) AS total_cost_cny,
                    SUM(COALESCE(est_weight_kg, 0)) AS weight_nom_kg,
                    SUM(COALESCE(total_bags, 0)) AS total_places
                FROM po_part
                WHERE po_id = ?
                  AND COALESCE(TRIM(po_part_id), '') <> ''
                """,
                (po_id,),
            ).fetchone()
            total_units = (
                _to_int(part_agg["total_units"])
                if part_agg and part_agg["total_units"] is not None
                else sum(r["order_qty"] for r in rows)
            )
            total_cost_cny = (
                _to_float(part_agg["total_cost_cny"])
                if part_agg and part_agg["total_cost_cny"] is not None
                else sum(r["line_cost_cny"] for r in rows)
            )
            weight_nom_kg = _to_float(part_agg["weight_nom_kg"]) if part_agg else 0.0
            total_places = _to_int(part_agg["total_places"]) if part_agg else 0

            part_status_rows = conn.execute(
                """
                SELECT DISTINCT UPPER(COALESCE(status, ''))
                FROM po_part
                WHERE po_id = ?
                  AND COALESCE(TRIM(po_part_id), '') <> ''
                """,
                (po_id,),
            ).fetchall()
            part_statuses = {str(r[0] or "").strip().upper() for r in part_status_rows}
            if "IN_TRANSIT" in part_statuses:
                header_status = "IN_TRANSIT"
            elif part_statuses and part_statuses == {"RECEIVED"}:
                header_status = "RECEIVED"
            else:
                header_status = _po_status(rows)
            payload = {
                "po_id": po_id,
                "supplier_code": rows[0]["supplier_id"] or "SHR",
                "message_date": rows[0]["message_date"],
                "ship_date_cargo": rows[0]["cargo_send_date"],
                "ast_arrival_nom": rows[0]["estimated_arrival_date"],
                "ast_arrival_real": rows[0]["actual_arrival_date"],
                "status": header_status,
                "units_total": total_units,
                "total_cost_cny": round(total_cost_cny, 2),
                "weight_nom_kg": round(weight_nom_kg, 3),
                "total_places": total_places,
            }
            usable = {k: v for k, v in payload.items() if k in header_cols}
            existing = conn.execute("SELECT 1 FROM po_header WHERE po_id = ? LIMIT 1", (po_id,)).fetchone()
            if existing:
                updates = ", ".join(f"{k} = ?" for k in usable.keys() if k != "po_id")
                params = [usable[k] for k in usable.keys() if k != "po_id"] + [po_id]
                conn.execute(f"UPDATE po_header SET {updates} WHERE po_id = ?", params)
                summary["updated"]["po_header"] += 1
            else:
                fields = ", ".join(usable.keys())
                placeholders = ", ".join(["?"] * len(usable))
                conn.execute(
                    f"INSERT INTO po_header ({fields}) VALUES ({placeholders})",
                    [usable[k] for k in usable.keys()],
                )
                summary["inserted"]["po_header"] += 1

        # Upsert po_line and dimension rows
        for row in valid_rows:
            _upsert_dim_sku(
                conn,
                row["sku_key"],
                row["base_cost_cny"],
                sku_price_map,
                allow_weight_overwrite=allow_dim_sku_weight_overwrite,
            )
            _upsert_dim_sku_size(conn, row["sku_id"], row["sku_key"], row["my_size"])

            existing = conn.execute(
                """
                SELECT po_line_id
                FROM po_line
                WHERE po_id = ? AND po_part_id = ? AND sku_key = ? AND my_size = ?
                LIMIT 1
                """,
                (row["po_id"], row["po_part_id"], row["sku_key"], row["my_size"]),
            ).fetchone()

            status = "RECEIVED" if row["status"] == "RECEIVED" else "IN_TRANSIT"
            if existing:
                conn.execute(
                    """
                    UPDATE po_line
                    SET sku_id = ?,
                        order_qty = ?,
                        received_qty = ?,
                        unit_cost_cny = ?,
                        status = ?
                    WHERE po_line_id = ?
                    """,
                    (
                        row["sku_id"],
                        row["order_qty"],
                        row["received_qty"] if status == "RECEIVED" else 0,
                        row["base_cost_cny"],
                        status,
                        existing["po_line_id"],
                    ),
                )
                summary["updated"]["po_line"] += 1
            else:
                conn.execute(
                    """
                    INSERT INTO po_line (
                        po_id, po_part_id, sku_key, sku_id, my_size,
                        order_qty, received_qty, unit_cost_cny, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["po_id"],
                        row["po_part_id"],
                        row["sku_key"],
                        row["sku_id"],
                        row["my_size"],
                        row["order_qty"],
                        row["received_qty"] if status == "RECEIVED" else 0,
                        row["base_cost_cny"],
                        status,
                    ),
                )
                summary["inserted"]["po_line"] += 1

        conn.commit()
    finally:
        conn.close()

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync PO parts from inbound calendar workbook")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Workbook path")
    parser.add_argument("--sheet-inbounds", default="Inbounds_sheet")
    parser.add_argument("--sheet-parts", default="PO_part_id_Totals")
    parser.add_argument("--sheet-sku", default="DIM_SKU_light_v5")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database path")
    parser.add_argument("--apply", action="store_true", help="Apply writes")
    parser.add_argument(
        "--allow-dim-sku-weight-overwrite",
        action="store_true",
        help="Allow workbook DIM_SKU_light_v5 rows to overwrite existing dim_sku.weight_kg",
    )
    args = parser.parse_args()

    try:
        summary = sync_po_parts_from_workbook(
            xlsx_path=args.xlsx,
            db_path=args.db,
            sheet_inbounds=args.sheet_inbounds,
            sheet_parts=args.sheet_parts,
            sheet_sku=args.sheet_sku,
            apply=args.apply,
            allow_dim_sku_weight_overwrite=args.allow_dim_sku_weight_overwrite,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        f"PO part sync {'APPLY' if args.apply else 'DRY-RUN'}: "
        f"inbounds_valid={summary['rows_inbounds_valid']} po_ids={len(summary['po_ids'])} "
        f"po_parts={len(summary['po_part_ids'])}"
    )
    if args.apply:
        print(
            "Writes:",
            f"inserted={summary['inserted']} updated={summary['updated']}",
        )
    if summary["warnings"]:
        print(f"Warnings: {len(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
