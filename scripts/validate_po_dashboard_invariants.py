#!/usr/bin/env python3
"""
Validate PO dashboard invariants for PLAN-0.

Checks:
- sum(size_level.order_qty) == sku_level.po_qty_total for sized SKUs
- no negative order_qty values
- no duplicate size codes per sku_key (case/format normalized)
- sum(d_size) ~= d_sku within tolerance
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


def _normalize_size(size: str | None) -> str:
    if not size:
        return ""
    return str(size).upper().replace(" ", "").replace("-", "")


def _plan_index(name: str) -> int:
    if not name.startswith("PLAN-"):
        return 0
    try:
        return int(name.split("-", 1)[1])
    except (ValueError, IndexError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PO dashboard invariants")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DASHBOARD_PATH,
        help="Dashboard JSON path (default: exports/po_dashboard_data.json)",
    )
    parser.add_argument(
        "--plan",
        type=str,
        default=None,
        help="Plan name to validate (default: active_pos[0] or PLAN-0)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Tolerance for d_size sum vs d_sku (default: 0.01)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"SKIP: dashboard output missing: {args.input}")
        return 0

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid dashboard JSON: {exc}")
        return 1

    pos = payload.get("pos", {})
    if not isinstance(pos, dict) or not pos:
        print("ERROR: dashboard output missing pos data")
        return 1

    plan_name = args.plan
    if not plan_name:
        active = payload.get("active_pos") or []
        if "PLAN-1" in pos:
            plan_name = "PLAN-1"
        elif active:
            plan_name = active[0]
        elif "PLAN-0" in pos:
            plan_name = "PLAN-0"
        else:
            plan_name = sorted(pos.keys(), key=_plan_index)[0]

    plan = pos.get(plan_name)
    if not isinstance(plan, dict):
        print(f"ERROR: plan not found: {plan_name}")
        return 1

    sku_level = plan.get("sku_level", [])
    size_level = plan.get("size_level", [])

    size_by_sku: dict[str, list[dict]] = {}
    for row in size_level:
        sku_key = row.get("sku_key")
        if not sku_key:
            continue
        size_by_sku.setdefault(sku_key, []).append(row)

    errors: list[str] = []

    for sku in sku_level:
        sku_key = sku.get("sku_key")
        if not sku_key:
            continue
        is_cl = str(sku_key).startswith("CL_")
        size_rows = size_by_sku.get(sku_key, [])

        # No negative order quantities
        if int(sku.get("po_qty_total", 0) or 0) < 0:
            errors.append(f"{sku_key}: negative po_qty_total")

        if not size_rows:
            continue

        # Duplicate size codes (normalized)
        seen = set()
        for row in size_rows:
            size = _normalize_size(row.get("size"))
            if not size:
                continue
            if size in seen:
                errors.append(f"{sku_key}: duplicate size code {size}")
                break
            seen.add(size)

        # Size-level order quantity sum equals sku-level total
        size_order_sum = sum(int(r.get("order_qty", 0) or 0) for r in size_rows)
        sku_total = int(sku.get("po_qty_total", 0) or 0)
        if size_order_sum != sku_total:
            errors.append(
                f"{sku_key}: size_order_sum={size_order_sum} != po_qty_total={sku_total}"
            )

        # No negative size order_qty
        for row in size_rows:
            if int(row.get("order_qty", 0) or 0) < 0:
                errors.append(f"{sku_key}: negative size order_qty for {row.get('size')}")
                break

        # Deficit-capped ordering for CL sizes
        if is_cl:
            for row in size_rows:
                try:
                    pre_arrival = float(row.get("pre_arrival", 0) or 0)
                    target = float(row.get("target", 0) or 0)
                    deficit = float(row.get("deficit_size", 0) or 0)
                    order_qty = int(row.get("order_qty", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if (target > 0 and pre_arrival >= target) or deficit <= 0:
                    if order_qty > 0:
                        errors.append(
                            f"{sku_key}: size {row.get('size')} has no deficit but order_qty={order_qty}"
                        )
                        break

        # d_size sum vs d_sku
        d_sku = float(sku.get("d_sku", 0) or 0)
        if d_sku > 0:
            d_size_sum = sum(float(r.get("d_size", 0) or 0) for r in size_rows)
            if abs(d_size_sum - d_sku) > args.tolerance:
                errors.append(
                    f"{sku_key}: sum(d_size)={d_size_sum:.4f} vs d_sku={d_sku:.4f}"
                )

    # PLAN chain DoC floor invariant
    plan_names = sorted(pos.keys(), key=_plan_index)
    base_plan_name = "PLAN-0" if "PLAN-0" in pos else plan_names[0]
    base_plan = pos.get(base_plan_name, {})
    base_r = float(base_plan.get("reorder_cycle_R", 0) or 0)
    base_map: dict[str, tuple[float, float]] = {}
    for sku in base_plan.get("sku_level", []):
        sku_key = sku.get("sku_key")
        if not sku_key:
            continue
        d_sku = float(sku.get("d_sku", 0) or 0)
        target = float(sku.get("target", 0) or 0)
        base_map[sku_key] = (d_sku, target)

    for idx in range(len(plan_names) - 1):
        curr_name = plan_names[idx]
        curr = pos.get(curr_name, {})
        if _plan_index(curr_name) < 1:
            continue
        nxt = pos.get(plan_names[idx + 1], {})
        curr_by_sku = {s.get("sku_key"): s for s in curr.get("sku_level", []) if s.get("sku_key")}
        for next_sku in nxt.get("sku_level", []):
            sku_key = next_sku.get("sku_key")
            if not sku_key:
                continue
            if not str(sku_key).startswith("CL_"):
                continue
            base_vals = base_map.get(sku_key)
            if not base_vals:
                continue
            base_d, base_target = base_vals
            if base_d <= 0:
                continue
            prev = curr_by_sku.get(sku_key, {})
            prev_order_qty = int(prev.get("po_qty_total", 0) or 0)
            if prev_order_qty <= 0:
                continue
            ss_total = max(0.0, base_target - (base_d * base_r))
            ss_total_days = ss_total / base_d if base_d > 0 else 0.0
            pre_arr_doc = float(next_sku.get("pre_arr_doc", 0) or 0)
            if pre_arr_doc < (ss_total_days - 0.25):
                errors.append(
                    f"{sku_key}: {plan_names[idx+1]} pre_arr_doc={pre_arr_doc:.2f} < "
                    f"SS_total/D={ss_total_days:.2f} (prev {plan_names[idx]} qty={prev_order_qty})"
                )

    if errors:
        print("INVARIANT FAILURES:")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... {len(errors) - 20} more")
        return 1

    print(f"OK: invariants passed for {plan_name} ({len(sku_level)} SKUs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
