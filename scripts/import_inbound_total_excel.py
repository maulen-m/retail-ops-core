#!/usr/bin/env python3
"""
Import inbound PO totals from a size-level Excel sheet.

Expected sheet: size_level
Required columns:
  - SKU Key
  - Size
  - message_date
  - Order Qty_Approved
  - PO_id
  - cargo_send_date
  - base_cost
  - PO Base (CNY)

Writes to:
  - po_header (upsert)
  - po_line (upsert)
  - dim_sku / dim_sku_size (activate + create missing sizes)
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import get_fx_rates
from core.db import DEFAULT_DB_PATH, get_db
from core.db.ledger import log_audit
from core.po.lifecycle import PO_STATUS_FLOW
from core.utils.sku_normalize import normalize_size


REQUIRED_COLS = [
    "SKU Key",
    "Size",
    "message_date",
    "Order Qty_Approved",
    "PO_id",
    "cargo_send_date",
    "base_cost",
    "PO Base (CNY)",
]


def _parse_date(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        raw = val.strip()
        if not raw:
            return None
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%d.%m.%y",
            "%d/%m/%y",
        ):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _to_float(val) -> Optional[float]:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return 0
        return int(round(float(val)))
    except (TypeError, ValueError):
        return 0


def _infer_product_type(sku_key: str) -> str:
    return "ELS" if sku_key.startswith("ELS_") else "CL"


def _normalize_size(size: str, product_type: str) -> str:
    if not size:
        return "ONE_SIZE" if product_type == "ELS" else ""
    normalized = normalize_size(size, product_type=product_type)
    return normalized or size


def _status_rank(status: str) -> int:
    try:
        return PO_STATUS_FLOW.index(status)
    except ValueError:
        return -1


def load_rows(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df


def build_report_rows(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        qty = _to_int(row.get("Order Qty_Approved"))
        if qty <= 0:
            continue
        sku_key = str(row.get("SKU Key") or "").strip()
        if not sku_key:
            continue
        raw_size = str(row.get("Size") or "").strip()
        po_id = str(row.get("PO_id") or "").strip()
        if not po_id:
            continue
        base_cost = _to_float(row.get("base_cost")) or 0.0
        po_base_cny = _to_float(row.get("PO Base (CNY)"))
        if po_base_cny is None or po_base_cny <= 0:
            po_base_cny = base_cost * qty
        message_date = _parse_date(row.get("message_date"))
        cargo_send_date = _parse_date(row.get("cargo_send_date"))
        product_type = _infer_product_type(sku_key)
        size = _normalize_size(raw_size, product_type)
        sku_id = f"{sku_key}_{size}" if size else sku_key

        rows.append(
            {
                "po_id": po_id,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": size,
                "qty": qty,
                "base_cost_cny": base_cost,
                "line_cost_cny": po_base_cny,
                "message_date": message_date,
                "cargo_send_date": cargo_send_date,
                "product_type": product_type,
            }
        )
    return rows


def write_report_md(
    report_path: Path,
    per_po: dict,
    fx_rates,
    lead_time_days: int,
) -> None:
    def fmt_date(val: Optional[str]) -> str:
        return val or "-"

    def fmt_num(val: float, decimals: int = 0) -> str:
        return f"{val:,.{decimals}f}".replace(",", " ")

    headers = [
        "PO",
        "Message",
        "Cargo Send",
        "Est Arrival",
        "Units",
        "Base CNY",
        "Base KZT",
        "Weight kg",
        "DLV USD",
        "DLV KZT",
        "COGS KZT",
    ]

    rows = []
    totals = {
        "units": 0,
        "base_cny": 0.0,
        "base_kzt": 0.0,
        "weight": 0.0,
        "dlv_usd": 0.0,
        "dlv_kzt": 0.0,
        "cogs_kzt": 0.0,
    }

    for po_id, meta in per_po.items():
        msg = meta.get("message_date")
        ship = meta.get("ship_date_cargo")
        est_arrival = "-"
        if ship:
            try:
                est = date.fromisoformat(ship) + timedelta(days=lead_time_days)
                est_arrival = est.isoformat()
            except ValueError:
                est_arrival = "-"
        units = meta.get("units_total", 0)
        base_cny = meta.get("total_cost_cny", 0.0)
        base_kzt = base_cny * fx_rates.cny_kzt
        weight = meta.get("weight_nom_kg", 0.0)
        dlv_usd = weight * fx_rates.dlv_rate_usd_kg
        dlv_kzt = dlv_usd * fx_rates.usd_kzt
        cogs_kzt = base_kzt + dlv_kzt

        totals["units"] += units
        totals["base_cny"] += base_cny
        totals["base_kzt"] += base_kzt
        totals["weight"] += weight
        totals["dlv_usd"] += dlv_usd
        totals["dlv_kzt"] += dlv_kzt
        totals["cogs_kzt"] += cogs_kzt

        rows.append(
            [
                po_id,
                fmt_date(msg),
                fmt_date(ship),
                est_arrival,
                str(units),
                fmt_num(base_cny, 0),
                fmt_num(base_kzt, 0),
                fmt_num(weight, 2),
                fmt_num(dlv_usd, 2),
                fmt_num(dlv_kzt, 0),
                fmt_num(cogs_kzt, 0),
            ]
        )

    def ascii_table(headers, rows):
        widths = [len(h) for h in headers]
        for row in rows:
            widths = [max(w, len(str(cell))) for w, cell in zip(widths, row)]
        sep = "| " + " | ".join("-" * w for w in widths) + " |"
        out = ["| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |", sep]
        for row in rows:
            out.append("| " + " | ".join(str(c).ljust(w) for c, w in zip(row, widths)) + " |")
        return "\n".join(out)

    overall_row = [
        "ALL",
        "-",
        "-",
        "-",
        str(totals["units"]),
        fmt_num(totals["base_cny"], 0),
        fmt_num(totals["base_kzt"], 0),
        fmt_num(totals["weight"], 2),
        fmt_num(totals["dlv_usd"], 2),
        fmt_num(totals["dlv_kzt"], 0),
        fmt_num(totals["cogs_kzt"], 0),
    ]

    report_lines = [
        "# Inbound Totals (2026-01-21)",
        "",
        "Source: `Inbound_total_21.1.2026.xlsx`",
        "",
        f"- FX rates used: CNY/KZT={fx_rates.cny_kzt}, USD/KZT={fx_rates.usd_kzt}, DLV_USD_KG={fx_rates.dlv_rate_usd_kg}",
        f"- Lead time used for ETA: {lead_time_days} days",
        "",
        "## Per-PO summary",
        "",
        ascii_table(headers, rows),
        "",
        "## Overall totals",
        "",
        ascii_table(headers, [overall_row]),
        "",
    ]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")


def import_inbound_total(
    xlsx_path: Path,
    sheet: str,
    supplier_code: str,
    db_path: Path,
    apply: bool,
    report_md: Optional[Path],
    lead_time_days: int,
) -> dict:
    df = load_rows(xlsx_path, sheet)
    rows = build_report_rows(df)
    if not rows:
        raise RuntimeError("No rows with Order Qty_Approved > 0")

    fx_rates = get_fx_rates(db_path=db_path)

    per_po: dict[str, dict] = {}
    for row in rows:
        po_id = row["po_id"]
        per_po.setdefault(
            po_id,
            {
                "message_date": None,
                "ship_date_cargo": None,
                "units_total": 0,
                "total_cost_cny": 0.0,
                "weight_nom_kg": 0.0,
            },
        )
        meta = per_po[po_id]
        meta["units_total"] += row["qty"]
        meta["total_cost_cny"] += row["line_cost_cny"]
        if row["message_date"]:
            meta["message_date"] = (
                row["message_date"]
                if meta["message_date"] is None
                else min(meta["message_date"], row["message_date"])
            )
        if row["cargo_send_date"]:
            meta["ship_date_cargo"] = (
                row["cargo_send_date"]
                if meta["ship_date_cargo"] is None
                else min(meta["ship_date_cargo"], row["cargo_send_date"])
            )

    inserted_po_ids: list[str] = []
    with get_db(db_path) as conn:
        # Cache weights and existing rows
        sku_weights = {
            row["sku_key"]: row["weight_kg"]
            for row in conn.execute("SELECT sku_key, weight_kg FROM dim_sku").fetchall()
        }

        if apply:
            # Ensure dim_sku + dim_sku_size
            for row in rows:
                sku_key = row["sku_key"]
                base_cost = row["base_cost_cny"]
                product_type = row["product_type"]

                existing = conn.execute(
                    "SELECT sku_key, base_cost_cny, weight_kg, product_type FROM dim_sku WHERE sku_key = ?",
                    (sku_key,),
                ).fetchone()

                if existing:
                    new_base = existing["base_cost_cny"] or base_cost or 0
                    new_type = existing["product_type"] or product_type
                    conn.execute(
                        """
                        UPDATE dim_sku
                           SET active_flag = 1,
                               base_cost_cny = ?,
                               product_type = ?,
                               updated_at = datetime('now')
                         WHERE sku_key = ?
                        """,
                        (new_base, new_type, sku_key),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO dim_sku (
                            sku_key, model, color, product_type,
                            base_cost_cny, weight_kg, category, gender,
                            active_flag, created_at, updated_at,
                            cogs_kzt, avg_sell_price_kzt_used, avg_sell_price_source, price_missing_flag
                        ) VALUES (
                            ?, ?, NULL, ?,
                            ?, 0, NULL, NULL,
                            1, datetime('now'), datetime('now'),
                            NULL, NULL, NULL, 1
                        )
                        """,
                        (sku_key, sku_key, product_type, base_cost or 0),
                    )

                sku_id = row["sku_id"]
                my_size = row["my_size"]
                if my_size:
                    exists = conn.execute(
                        "SELECT sku_id FROM dim_sku_size WHERE sku_id = ?",
                        (sku_id,),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            """
                            INSERT INTO dim_sku_size (
                                sku_id, sku_key, my_size, barcode, size_order, active_flag, created_at
                            ) VALUES (?, ?, ?, NULL, NULL, 1, datetime('now'))
                            """,
                            (sku_id, sku_key, my_size),
                        )

            # Upsert po_header
            for po_id, meta in per_po.items():
                existing = conn.execute(
                    "SELECT status, supplier_code, fx_rate_cny_plan, cargo_rate_usd_kg FROM po_header WHERE po_id = ?",
                    (po_id,),
                ).fetchone()

                msg_date = meta["message_date"]
                ship_date_cargo = meta["ship_date_cargo"]
                units_total = meta["units_total"]
                total_cost_cny = meta["total_cost_cny"]

                for row in rows:
                    if row["po_id"] != po_id:
                        continue
                    weight = sku_weights.get(row["sku_key"], 0) or 0
                    meta["weight_nom_kg"] += weight * row["qty"]

                status = "DRAFT"
                if msg_date:
                    status = "SENT"
                if ship_date_cargo:
                    status = "SHIPPED_CARGO"

                if existing:
                    current_status = existing["status"] or status
                    if _status_rank(status) > _status_rank(current_status):
                        current_status = status

                    updates = {
                        "message_date": msg_date,
                        "ship_date_cargo": ship_date_cargo,
                        "units_total": units_total,
                        "total_cost_cny": total_cost_cny,
                        "weight_nom_kg": meta["weight_nom_kg"],
                        "status": current_status,
                        "supplier_code": existing["supplier_code"] or supplier_code,
                        "fx_rate_cny_plan": existing["fx_rate_cny_plan"] or fx_rates.cny_kzt,
                        "cargo_rate_usd_kg": existing["cargo_rate_usd_kg"] or fx_rates.dlv_rate_usd_kg,
                    }

                    set_clause = ", ".join(f"{k} = ?" for k in updates.keys() if updates[k] is not None)
                    values = [v for k, v in updates.items() if v is not None]
                    values.append(po_id)
                    conn.execute(
                        f"UPDATE po_header SET {set_clause}, updated_at = datetime('now') WHERE po_id = ?",
                        values,
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO po_header (
                            po_id, supplier_code, message_date, ship_date_cargo,
                            status, units_total, units_received, total_cost_cny,
                            weight_nom_kg, fx_rate_cny_plan, cargo_rate_usd_kg,
                            created_at, updated_at
                        ) VALUES (
                            ?, ?, ?, ?,
                            ?, ?, 0, ?,
                            ?, ?, ?,
                            datetime('now'), datetime('now')
                        )
                        """,
                        (
                            po_id,
                            supplier_code,
                            msg_date,
                            ship_date_cargo,
                            status,
                            units_total,
                            total_cost_cny,
                            meta["weight_nom_kg"],
                            fx_rates.cny_kzt,
                            fx_rates.dlv_rate_usd_kg,
                        ),
                    )
                    inserted_po_ids.append(po_id)

            # Upsert po_line
            for row in rows:
                po_id = row["po_id"]
                sku_id = row["sku_id"]
                sku_key = row["sku_key"]
                my_size = row["my_size"]
                qty = row["qty"]
                unit_cost_cny = row["base_cost_cny"]
                unit_weight = sku_weights.get(sku_key, 0) or 0

                existing = conn.execute(
                    "SELECT po_line_id, received_qty, status FROM po_line WHERE po_id = ? AND sku_id = ?",
                    (po_id, sku_id),
                ).fetchone()

                if existing:
                    received_qty = existing["received_qty"] or 0
                    status = existing["status"] or "PENDING"
                    conn.execute(
                        """
                        UPDATE po_line
                           SET sku_key = ?,
                               my_size = ?,
                               order_qty = ?,
                               received_qty = ?,
                               unit_cost_cny = ?,
                               unit_weight_kg = ?,
                               status = ?,
                               updated_at = datetime('now')
                         WHERE po_line_id = ?
                        """,
                        (
                            sku_key,
                            my_size,
                            qty,
                            received_qty,
                            unit_cost_cny,
                            unit_weight,
                            status,
                            existing["po_line_id"],
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO po_line (
                            po_id, sku_key, sku_id, my_size,
                            order_qty, received_qty, unit_cost_cny, unit_weight_kg,
                            status, created_at, updated_at
                        ) VALUES (
                            ?, ?, ?, ?,
                            ?, 0, ?, ?,
                            'PENDING', datetime('now'), datetime('now')
                        )
                        """,
                        (
                            po_id,
                            sku_key,
                            sku_id,
                            my_size,
                            qty,
                            unit_cost_cny,
                            unit_weight,
                        ),
                    )

    for po_id in inserted_po_ids:
        log_audit(
            table_name="po_header",
            record_id=po_id,
            field_name="*",
            old_value=None,
            new_value=f"Imported from {xlsx_path.name}",
            change_type="INSERT",
            source="IMPORT",
            db_path=db_path,
        )

    if report_md:
        write_report_md(report_md, per_po, fx_rates, lead_time_days)

    return {
        "po_count": len(per_po),
        "line_count": len(rows),
        "po_ids": sorted(per_po.keys()),
        "report_md": str(report_md) if report_md else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import inbound totals from Excel size_level sheet")
    parser.add_argument("xlsx_path", type=Path, help="Path to Inbound_total_21.1.2026.xlsx")
    parser.add_argument("--sheet", default="size_level", help="Sheet name (default: size_level)")
    parser.add_argument("--supplier-code", default="SUPP_A", help="Supplier code (default: SUPP_A)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to database")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--report-md", type=Path, help="Write markdown summary to this path")
    parser.add_argument("--lead-time-days", type=int, default=21, help="Lead time for ETA calc")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    xlsx_path = args.xlsx_path.expanduser()

    result = import_inbound_total(
        xlsx_path=xlsx_path,
        sheet=args.sheet,
        supplier_code=args.supplier_code,
        db_path=db_path,
        apply=args.apply,
        report_md=args.report_md,
        lead_time_days=args.lead_time_days,
    )

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] Imported {result['line_count']} rows across {result['po_count']} POs")
    print(f"POs: {', '.join(result['po_ids'])}")
    if result["report_md"]:
        print(f"Report: {result['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
