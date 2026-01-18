#!/usr/bin/env python3
"""
Debug PO plan-chain computations for a specific SKU.

Outputs a JSON + CSV snapshot of key plan variables to exports/.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "exports"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_po_dashboard_data as gen  # type: ignore


def _normalize_sku(value: str | None) -> str:
    return str(value or "").strip().lower()


def _match_sku_key(target: str, candidates: list[str]) -> str | None:
    if not target:
        return None
    target_norm = _normalize_sku(target)
    for cand in candidates:
        if _normalize_sku(cand) == target_norm:
            return cand
    for cand in candidates:
        if target_norm in _normalize_sku(cand):
            return cand
    return None


def _plan_index(name: str) -> int:
    if not name.startswith("PLAN-"):
        return 0
    try:
        return int(name.split("-", 1)[1])
    except (ValueError, IndexError):
        return 0


def _load_base_ss_total(base_plan: dict, sku_key: str) -> tuple[float, float]:
    r_days = float(base_plan.get("reorder_cycle_R", 0) or 0)
    sku_line = next((s for s in base_plan.get("sku_level", []) if s.get("sku_key") == sku_key), None)
    if not sku_line:
        return 0.0, r_days
    d_sku = float(sku_line.get("d_sku", 0) or 0)
    target = float(sku_line.get("target", 0) or 0)
    ss_total = max(0.0, target - (d_sku * r_days)) if d_sku > 0 else 0.0
    return ss_total, r_days


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug PO plan-chain for a SKU")
    parser.add_argument("--sku-key", required=True, help="SKU key (exact or partial)")
    parser.add_argument("--plan", default="PLAN-2", help="Plan name (default: PLAN-2)")
    parser.add_argument("--as-of", default=None, help="As-of date (YYYY-MM-DD)")
    parser.add_argument("--db", default=None, help="DB path (optional)")
    args = parser.parse_args()

    if args.db:
        gen.DB_PATH = Path(args.db).expanduser()

    if args.as_of:
        as_of_date = date.fromisoformat(args.as_of)
        gen.CUTOFF_DATE = as_of_date
        gen.DATA_CUTOFF = as_of_date.isoformat()
        gen.STOCK_DATE = as_of_date.isoformat()
        gen.TODAY = as_of_date
        gen.get_stock_snapshot_date = lambda: as_of_date.isoformat()  # type: ignore

    pos = gen.generate_multi_po_data()
    if not pos:
        print("ERROR: no plan data produced")
        return 1

    plan_names = sorted(pos.keys(), key=_plan_index)
    sku_candidates = []
    for plan in pos.values():
        for sku in plan.get("sku_level", []):
            if sku.get("sku_key"):
                sku_candidates.append(str(sku["sku_key"]))
    sku_key = _match_sku_key(args.sku_key, sorted(set(sku_candidates)))
    if not sku_key:
        print(f"ERROR: sku not found for key: {args.sku_key}")
        return 1

    base_plan = pos.get("PLAN-0") or pos.get(plan_names[0], {})
    ss_total, base_r = _load_base_ss_total(base_plan, sku_key)

    rows: list[dict[str, object]] = []
    prev_order_qty = 0
    ss_total_days = 0.0

    for name in plan_names:
        plan = pos.get(name, {})
        sku_line = next((s for s in plan.get("sku_level", []) if s.get("sku_key") == sku_key), None)
        if not sku_line:
            continue
        d_sku = float(sku_line.get("d_sku", 0) or 0)
        ss_total_days = (ss_total / d_sku) if d_sku > 0 else 0.0
        pre_arr_doc = float(sku_line.get("pre_arr_doc", 0) or 0)
        po_qty_total = int(sku_line.get("po_qty_total", 0) or 0)
        floor_violation = (
            d_sku > 0
            and prev_order_qty > 0
            and pre_arr_doc < (ss_total_days - 0.25)
        )
        rows.append(
            {
                "plan_name": name,
                "plan_index": _plan_index(name),
                "po_message_date": plan.get("po_message_date"),
                "po_send_date": sku_line.get("po_send_date"),
                "est_arr_date": sku_line.get("est_arr_date"),
                "days_until_arrival": sku_line.get("days_until_arrival"),
                "d_sku": d_sku,
                "ss_total": round(ss_total, 2),
                "ss_total_days": round(ss_total_days, 2),
                "base_R": base_r,
                "stock": sku_line.get("stock"),
                "inbound": sku_line.get("inbound"),
                "active_inbound": sku_line.get("active_inbound"),
                "inbound_total": sku_line.get("inbound_total"),
                "consumption_until_arrival": sku_line.get("consumption_until_arrival"),
                "pre_arrival": sku_line.get("pre_arrival"),
                "pre_arr_doc": pre_arr_doc,
                "t_post_days": sku_line.get("t_post_days"),
                "target": sku_line.get("target"),
                "po_qty_total": po_qty_total,
                "prev_plan_po_qty_total": prev_order_qty,
                "floor_violation": floor_violation,
            }
        )
        prev_order_qty = po_qty_total

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_key = sku_key.replace("/", "_").replace(" ", "_")
    as_of_label = (args.as_of or gen.STOCK_DATE or gen.TODAY.isoformat()).replace("-", "")
    json_path = EXPORT_DIR / f"plan_chain_debug_{safe_key}_{as_of_label}.json"
    csv_path = EXPORT_DIR / f"plan_chain_debug_{safe_key}_{as_of_label}.csv"

    payload = {
        "sku_key": sku_key,
        "as_of": args.as_of or gen.STOCK_DATE,
        "base_plan": base_plan.get("po_name", "PLAN-0"),
        "ss_total": round(ss_total, 2),
        "ss_total_days": round(ss_total_days, 2),
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
