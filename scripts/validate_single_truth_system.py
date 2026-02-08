#!/usr/bin/env python3
"""Validate workbook->DB->dashboard single-truth consistency at po_part grain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_DASHBOARD = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_CASHFLOW_CSV = PROJECT_ROOT / "exports" / "cashflow_calendar.csv"
DEFAULT_WORKBOOK = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/"
    "Purchase_orders/vibe_code_PO/backup/7.2.26/Inbound_calendar_V10.002.xlsx"
)


def _is_valid_part_id(raw: Any) -> bool:
    txt = str(raw or "").strip()
    if not txt:
        return False
    upper = txt.upper()
    if any(tok in upper for tok in ("TOTAL", "PENDING", "UNPAID", "PAYMENT")):
        return False
    return bool(re.match(r"^(PO[-_].+|ARC[-_].+|.+_PO-\d+)$", upper))


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_paid_flag(value: Any) -> int:
    txt = str(value or "").strip().upper()
    if txt in {"YES", "Y", "TRUE", "1", "PAID"}:
        return 1
    if txt in {"NO", "N", "FALSE", "0", "", "UNPAID"}:
        return 0
    try:
        return 1 if float(txt) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _load_workbook_parts(workbook_path: Path) -> dict[str, dict[str, Any]]:
    df = pd.read_excel(workbook_path, sheet_name="PO_part_id_Totals", dtype=object)
    required = {"PO_part_id", "is_paid_BASE", "is_paid_DLV", "To_pay_BASE_KZT", "To_pay_DLV_KZT"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"PO_part_id_Totals missing columns: {', '.join(missing)}")

    parts: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        po_part_id = str(row.get("PO_part_id") or "").strip()
        if not _is_valid_part_id(po_part_id):
            continue
        parts[po_part_id] = {
            "is_paid_base": _to_paid_flag(row.get("is_paid_BASE")),
            "is_paid_dlv": _to_paid_flag(row.get("is_paid_DLV")),
            "to_pay_base_kzt": _to_float(row.get("To_pay_BASE_KZT")),
            "to_pay_dlv_kzt": _to_float(row.get("To_pay_DLV_KZT")),
            "est_weight_kg": _to_float(row.get("Est. Weight (kg)")),
            "total_bags": int(round(_to_float(row.get("Total Bags")))),
            "total_units": int(round(_to_float(row.get("Total Units")))),
        }
    return parts


def _load_db_parts(db_path: Path) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                po_part_id, po_id, status, est_weight_kg, total_bags, total_units,
                COALESCE(is_paid_base, 0) AS is_paid_base,
                COALESCE(is_paid_dlv, 0) AS is_paid_dlv,
                COALESCE(to_pay_base_kzt, 0) AS to_pay_base_kzt,
                COALESCE(to_pay_dlv_kzt, 0) AS to_pay_dlv_kzt
            FROM po_part
            WHERE COALESCE(TRIM(po_part_id), '') <> ''
            """
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        part_id = str(row["po_part_id"] or "").strip()
        if not _is_valid_part_id(part_id):
            continue
        out[part_id] = {
            "po_id": row["po_id"],
            "status": row["status"],
            "est_weight_kg": _to_float(row["est_weight_kg"]),
            "total_bags": int(round(_to_float(row["total_bags"]))),
            "total_units": int(round(_to_float(row["total_units"]))),
            "is_paid_base": int(row["is_paid_base"] or 0),
            "is_paid_dlv": int(row["is_paid_dlv"] or 0),
            "to_pay_base_kzt": _to_float(row["to_pay_base_kzt"]),
            "to_pay_dlv_kzt": _to_float(row["to_pay_dlv_kzt"]),
        }
    return out


def validate_system(
    *,
    db_path: Path,
    workbook_path: Path,
    dashboard_path: Path,
    tol_kzt: float = 1.0,
    tol_weight: float = 0.1,
) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return [f"db not found: {db_path}"]
    if not workbook_path.exists():
        return [f"workbook not found: {workbook_path}"]
    if not dashboard_path.exists():
        return [f"dashboard JSON not found: {dashboard_path}"]

    workbook_parts = _load_workbook_parts(workbook_path)
    db_parts = _load_db_parts(db_path)
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

    wb_ids = set(workbook_parts.keys())
    db_ids = set(db_parts.keys())

    missing_in_db = sorted(wb_ids - db_ids)
    if missing_in_db:
        errors.append(f"workbook part ids missing in db: {', '.join(missing_in_db[:20])}")
    extra_in_db = sorted(db_ids - wb_ids)
    if extra_in_db:
        errors.append(f"db part ids missing in workbook: {', '.join(extra_in_db[:20])}")

    for part_id in sorted(wb_ids & db_ids):
        wb = workbook_parts[part_id]
        db = db_parts[part_id]
        if int(wb["is_paid_base"]) != int(db["is_paid_base"]):
            errors.append(
                f"{part_id}: is_paid_BASE workbook={wb['is_paid_base']} db={db['is_paid_base']}"
            )
        if int(wb["is_paid_dlv"]) != int(db["is_paid_dlv"]):
            errors.append(
                f"{part_id}: is_paid_DLV workbook={wb['is_paid_dlv']} db={db['is_paid_dlv']}"
            )
        if abs(float(wb["to_pay_base_kzt"]) - float(db["to_pay_base_kzt"])) > tol_kzt:
            errors.append(
                f"{part_id}: To_pay_BASE_KZT workbook={wb['to_pay_base_kzt']} db={db['to_pay_base_kzt']}"
            )
        if abs(float(wb["to_pay_dlv_kzt"]) - float(db["to_pay_dlv_kzt"])) > tol_kzt:
            errors.append(
                f"{part_id}: To_pay_DLV_KZT workbook={wb['to_pay_dlv_kzt']} db={db['to_pay_dlv_kzt']}"
            )

    archived = set(dashboard.get("archived_pos") or [])
    missing_archived = sorted(db_ids - archived)
    if missing_archived:
        errors.append(f"db part ids missing in dashboard archived_pos: {', '.join(missing_archived[:20])}")

    pos = dashboard.get("pos") or {}
    missing_pos = sorted(db_ids - set(pos.keys()))
    if missing_pos:
        errors.append(f"db part ids missing in dashboard pos entries: {', '.join(missing_pos[:20])}")

    real_pos_rows = {str(row.get("po_id")): row for row in (dashboard.get("real_pos") or []) if isinstance(row, dict)}
    for part_id in sorted(db_ids):
        db_row = db_parts[part_id]
        row = real_pos_rows.get(part_id)
        if not row:
            errors.append(f"{part_id}: missing from dashboard real_pos lifecycle")
            continue
        if abs(_to_float(row.get("weight_nom_kg")) - float(db_row["est_weight_kg"])) > tol_weight:
            errors.append(
                f"{part_id}: lifecycle weight mismatch dashboard={row.get('weight_nom_kg')} db={db_row['est_weight_kg']}"
            )
        if int(round(_to_float(row.get("total_places")))) != int(db_row["total_bags"]):
            errors.append(
                f"{part_id}: lifecycle bags mismatch dashboard={row.get('total_places')} db={db_row['total_bags']}"
            )

    if DEFAULT_CASHFLOW_CSV.exists():
        try:
            cash_df = pd.read_csv(DEFAULT_CASHFLOW_CSV)
            if "receivables_close" in cash_df.columns:
                latest = cash_df.tail(30)
                leaked = latest[latest["receivables_close"].fillna(0).abs() > tol_kzt]
                if not leaked.empty:
                    errors.append(
                        "cashflow paid-default leakage: receivables_close is non-zero in cashflow_calendar.csv"
                    )
        except Exception as exc:
            errors.append(f"cashflow_csv_check error: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate workbook/DB/dashboard single truth")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    args = parser.parse_args()

    try:
        errors = validate_system(
            db_path=args.db,
            workbook_path=args.xlsx,
            dashboard_path=args.dashboard,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if errors:
        print("SINGLE-TRUTH FAILURES:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK: single-truth system validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
