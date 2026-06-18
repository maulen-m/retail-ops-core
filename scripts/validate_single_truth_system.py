#!/usr/bin/env python3
"""Validate workbook->DB->dashboard single-truth consistency at po_part grain."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_DASHBOARD = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_CASHFLOW_CSV = PROJECT_ROOT / "exports" / "cashflow_calendar.csv"
DEFAULT_WORKBOOK = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
DEFAULT_PO_PART_SCOPE_CONTRACT = PROJECT_ROOT / "config" / "validation" / "po_part_current_scope_contract.tsv"
PO_PART_TOTALS_COLUMN_ALIASES = {
    "To_pay_BASE_KZT (live)": "To_pay_BASE_KZT",
    "To_pay_BASE_KZT_reference": "To_pay_BASE_KZT",
    "To_pay_DLV_KZT (live)": "To_pay_DLV_KZT",
}
HISTORICAL_DB_ONLY_DECISION = "HISTORICAL_DB_ONLY_OUT_OF_CURRENT_WORKBOOK_SCOPE"


def resolve_workbook_path(workbook_path: Path | None = None) -> Path:
    """Resolve inbound workbook source with explicit > env > anchored default precedence."""
    if workbook_path is not None:
        return Path(workbook_path).expanduser()
    env_raw = str(os.environ.get("AB_INBOUND_WORKBOOK_PATH", "")).strip()
    if env_raw:
        return Path(env_raw).expanduser()
    return DEFAULT_WORKBOOK


def resolve_po_part_scope_contract(path: Path | None = None) -> Path | None:
    if path is not None:
        return Path(path).expanduser()
    env_raw = str(os.environ.get("AB_PO_PART_SCOPE_CONTRACT", "")).strip()
    if env_raw:
        return Path(env_raw).expanduser()
    if DEFAULT_PO_PART_SCOPE_CONTRACT.exists():
        return DEFAULT_PO_PART_SCOPE_CONTRACT
    return None


def _parse_false(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"false", "0", "no", "n"}


def _load_po_part_scope_contract(path: Path | None) -> set[str]:
    if path is None:
        return set()
    resolved = path.expanduser()
    if not resolved.exists():
        raise RuntimeError(f"PO part scope contract not found: {resolved}")
    df = pd.read_csv(resolved, sep="\t", dtype=str, keep_default_na=False)
    required = {"po_part_id", "canonical_decision", "production_authority"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(
            f"PO part scope contract missing required columns: {', '.join(missing)}"
        )

    scoped: set[str] = set()
    for idx, row in df.iterrows():
        row_number = int(idx) + 2
        part_id = str(row.get("po_part_id") or "").strip()
        decision = str(row.get("canonical_decision") or "").strip()
        if not part_id:
            raise RuntimeError(f"PO part scope contract row {row_number} missing po_part_id")
        if decision != HISTORICAL_DB_ONLY_DECISION:
            raise RuntimeError(
                f"PO part scope contract row {row_number} has unsupported decision: {decision}"
            )
        if not _parse_false(row.get("production_authority")):
            raise RuntimeError(
                f"PO part scope contract row {row_number} requires production_authority=false"
            )
        scoped.add(part_id)
    return scoped


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
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(number):
        return 0.0
    return number


def _to_int(value: Any) -> int:
    number = _to_float(value)
    if pd.isna(number):
        return 0
    return int(round(number))


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonicalize_po_part_totals_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map explicit workbook display aliases to canonical parser columns."""
    rename: dict[Any, str] = {}
    seen: dict[str, Any] = {}
    for col in df.columns:
        label = _normalize_header(col)
        canonical = PO_PART_TOTALS_COLUMN_ALIASES.get(label, label)
        if canonical in seen:
            raise RuntimeError(
                "PO_part_id_Totals ambiguous columns for "
                f"{canonical}: {seen[canonical]!r}, {col!r}"
            )
        seen[canonical] = col
        rename[col] = canonical
    return df.rename(columns=rename)


def _to_iso_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            serial = float(value)
            if serial > 0:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")).date().isoformat()
        except Exception:
            pass
    raw = _to_text(value)
    if not raw:
        return ""
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        try:
            serial = float(raw)
            if serial > 0:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")).date().isoformat()
        except Exception:
            pass
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    for fmt in ("%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw[:10] if len(raw) >= 10 else raw


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


def _normalize_status(value: Any) -> str:
    txt = _to_text(value).upper().replace(" ", "_")
    if txt in {"ARRIVED", "RECEIVED", "DONE"}:
        return "RECEIVED"
    if txt in {"TRANSIT", "IN_TRANSIT", "IN-TRANSIT", "SHIPPED", "SHIPPED_CARGO"}:
        return "IN_TRANSIT"
    return txt


def _load_workbook_parts(workbook_path: Path) -> dict[str, dict[str, Any]]:
    df = _canonicalize_po_part_totals_columns(
        pd.read_excel(workbook_path, sheet_name="PO_part_id_Totals", dtype=object)
    )
    required = {
        "PO_part_id",
        "Status",
        "Cargo_freight_id",
        "Actual_DLV_PAY_date",
        "is_paid_BASE",
        "is_paid_DLV",
        "To_pay_BASE_KZT",
        "To_pay_DLV_KZT",
        "Est. Weight (kg)",
        "Total Bags",
        "Total Units",
        "Actual_Weight_kg",
        "Paid_DLV_USD",
        "Paid_DLV_KZT",
        "Final_USD_per_kg",
        "USD_KZT_rate",
        "Actual_DLV_days",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"PO_part_id_Totals missing columns: {', '.join(missing)}")

    parts: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        po_part_id = str(row.get("PO_part_id") or "").strip()
        if not _is_valid_part_id(po_part_id):
            continue
        parts[po_part_id] = {
            "status": _normalize_status(row.get("Status")),
            "cargo_freight_id": _to_text(row.get("Cargo_freight_id")),
            "actual_dlv_pay_date": _to_iso_date(row.get("Actual_DLV_PAY_date")),
            "is_paid_base": _to_paid_flag(row.get("is_paid_BASE")),
            "is_paid_dlv": _to_paid_flag(row.get("is_paid_DLV")),
            "to_pay_base_kzt": _to_float(row.get("To_pay_BASE_KZT")),
            "to_pay_dlv_kzt": _to_float(row.get("To_pay_DLV_KZT")),
            "est_weight_kg": _to_float(row.get("Est. Weight (kg)")),
            "total_bags": _to_int(row.get("Total Bags")),
            "total_units": _to_int(row.get("Total Units")),
            "actual_weight_kg": _to_float(row.get("Actual_Weight_kg")),
            "paid_dlv_usd": _to_float(row.get("Paid_DLV_USD")),
            "paid_dlv_kzt": _to_float(row.get("Paid_DLV_KZT")),
            "final_usd_per_kg": _to_float(row.get("Final_USD_per_kg")),
            "usd_kzt_rate": _to_float(row.get("USD_KZT_rate")),
            "actual_dlv_days": _to_int(row.get("Actual_DLV_days")),
        }
    return parts


def _load_db_parts(db_path: Path) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                po_part_id, po_id, status, cargo_freight_id, actual_dlv_pay_date,
                est_weight_kg, actual_weight_kg, total_bags, total_units,
                COALESCE(paid_dlv_usd, 0) AS paid_dlv_usd,
                COALESCE(paid_dlv_kzt, 0) AS paid_dlv_kzt,
                COALESCE(final_usd_per_kg, 0) AS final_usd_per_kg,
                COALESCE(usd_kzt_rate, 0) AS usd_kzt_rate,
                COALESCE(actual_dlv_days, 0) AS actual_dlv_days,
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
            "status": _normalize_status(row["status"]),
            "cargo_freight_id": _to_text(row["cargo_freight_id"]),
            "actual_dlv_pay_date": _to_iso_date(row["actual_dlv_pay_date"]),
            "est_weight_kg": _to_float(row["est_weight_kg"]),
            "actual_weight_kg": _to_float(row["actual_weight_kg"]),
            "total_bags": _to_int(row["total_bags"]),
            "total_units": _to_int(row["total_units"]),
            "paid_dlv_usd": _to_float(row["paid_dlv_usd"]),
            "paid_dlv_kzt": _to_float(row["paid_dlv_kzt"]),
            "final_usd_per_kg": _to_float(row["final_usd_per_kg"]),
            "usd_kzt_rate": _to_float(row["usd_kzt_rate"]),
            "actual_dlv_days": _to_int(row["actual_dlv_days"]),
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
    po_part_scope_contract: Path | None = None,
    tol_kzt: float = 1.0,
    tol_weight: float = 0.1,
    tol_usd: float = 0.05,
    tol_rate: float = 0.01,
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
    scoped_historical_db_only_ids = _load_po_part_scope_contract(po_part_scope_contract)

    wb_ids = set(workbook_parts.keys())
    db_ids = set(db_parts.keys())
    unknown_scoped_ids = sorted(scoped_historical_db_only_ids - db_ids)
    if unknown_scoped_ids:
        errors.append(
            "PO part scope contract ids missing in db: "
            + ", ".join(unknown_scoped_ids[:20])
        )

    missing_in_db = sorted(wb_ids - db_ids)
    if missing_in_db:
        errors.append(f"workbook part ids missing in db: {', '.join(missing_in_db[:20])}")
    extra_in_db = sorted((db_ids - wb_ids) - scoped_historical_db_only_ids)
    if extra_in_db:
        errors.append(f"db part ids missing in workbook: {', '.join(extra_in_db[:20])}")

    for part_id in sorted(wb_ids & db_ids):
        wb = workbook_parts[part_id]
        db = db_parts[part_id]
        if wb["status"] != db["status"]:
            errors.append(f"{part_id}: status workbook={wb['status']} db={db['status']}")
        if _to_text(wb["cargo_freight_id"]) != _to_text(db["cargo_freight_id"]):
            errors.append(
                f"{part_id}: Cargo_freight_id workbook={wb['cargo_freight_id']} db={db['cargo_freight_id']}"
            )
        if _to_iso_date(wb["actual_dlv_pay_date"]) != _to_iso_date(db["actual_dlv_pay_date"]):
            errors.append(
                f"{part_id}: Actual_DLV_PAY_date workbook={wb['actual_dlv_pay_date']} db={db['actual_dlv_pay_date']}"
            )
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
        if abs(float(wb["est_weight_kg"]) - float(db["est_weight_kg"])) > tol_weight:
            errors.append(
                f"{part_id}: Est. Weight workbook={wb['est_weight_kg']} db={db['est_weight_kg']}"
            )
        if int(wb["total_bags"]) != int(db["total_bags"]):
            errors.append(f"{part_id}: Total Bags workbook={wb['total_bags']} db={db['total_bags']}")
        if int(wb["total_units"]) != int(db["total_units"]):
            errors.append(f"{part_id}: Total Units workbook={wb['total_units']} db={db['total_units']}")
        if abs(float(wb["actual_weight_kg"]) - float(db["actual_weight_kg"])) > tol_weight:
            errors.append(
                f"{part_id}: Actual_Weight_kg workbook={wb['actual_weight_kg']} db={db['actual_weight_kg']}"
            )
        if abs(float(wb["paid_dlv_usd"]) - float(db["paid_dlv_usd"])) > tol_usd:
            errors.append(
                f"{part_id}: Paid_DLV_USD workbook={wb['paid_dlv_usd']} db={db['paid_dlv_usd']}"
            )
        if abs(float(wb["paid_dlv_kzt"]) - float(db["paid_dlv_kzt"])) > tol_kzt:
            errors.append(
                f"{part_id}: Paid_DLV_KZT workbook={wb['paid_dlv_kzt']} db={db['paid_dlv_kzt']}"
            )
        if abs(float(wb["final_usd_per_kg"]) - float(db["final_usd_per_kg"])) > tol_rate:
            errors.append(
                f"{part_id}: Final_USD_per_kg workbook={wb['final_usd_per_kg']} db={db['final_usd_per_kg']}"
            )
        if abs(float(wb["usd_kzt_rate"]) - float(db["usd_kzt_rate"])) > tol_rate:
            errors.append(
                f"{part_id}: USD_KZT_rate workbook={wb['usd_kzt_rate']} db={db['usd_kzt_rate']}"
            )
        if int(wb["actual_dlv_days"]) != int(db["actual_dlv_days"]):
            errors.append(
                f"{part_id}: Actual_DLV_days workbook={wb['actual_dlv_days']} db={db['actual_dlv_days']}"
            )

    archived = set(dashboard.get("archived_pos") or [])
    current_db_ids = db_ids - scoped_historical_db_only_ids
    missing_archived = sorted(current_db_ids - archived)
    if missing_archived:
        errors.append(f"db part ids missing in dashboard archived_pos: {', '.join(missing_archived[:20])}")

    pos = dashboard.get("pos") or {}
    missing_pos = sorted(current_db_ids - set(pos.keys()))
    if missing_pos:
        errors.append(f"db part ids missing in dashboard pos entries: {', '.join(missing_pos[:20])}")

    real_pos_rows = {str(row.get("po_id")): row for row in (dashboard.get("real_pos") or []) if isinstance(row, dict)}
    for part_id in sorted(current_db_ids):
        db_row = db_parts[part_id]
        row = real_pos_rows.get(part_id)
        if not row:
            errors.append(f"{part_id}: missing from dashboard real_pos lifecycle")
            continue
        expected_weight = (
            float(db_row["actual_weight_kg"])
            if db_row["status"] == "RECEIVED" and float(db_row["actual_weight_kg"]) > 0
            else float(db_row["est_weight_kg"])
        )
        if abs(_to_float(row.get("weight_nom_kg")) - expected_weight) > tol_weight:
            errors.append(
                f"{part_id}: lifecycle weight mismatch dashboard={row.get('weight_nom_kg')} db_expected={expected_weight}"
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
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=None,
        help=(
            "Inbound workbook path (default resolves via AB_INBOUND_WORKBOOK_PATH, "
            f"then {DEFAULT_WORKBOOK})"
        ),
    )
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument(
        "--po-part-scope-contract",
        type=Path,
        default=None,
        help=(
            "TSV contract listing DB-only historical PO part IDs that are out "
            "of current workbook scope. Defaults to config/validation when present."
        ),
    )
    args = parser.parse_args()

    try:
        workbook_path = resolve_workbook_path(args.xlsx)
        scope_contract = resolve_po_part_scope_contract(args.po_part_scope_contract)
        errors = validate_system(
            db_path=args.db,
            workbook_path=workbook_path,
            dashboard_path=args.dashboard,
            po_part_scope_contract=scope_contract,
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
