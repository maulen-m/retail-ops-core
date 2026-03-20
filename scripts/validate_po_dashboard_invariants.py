#!/usr/bin/env python3
"""
Validate PO dashboard invariants for PLAN-0.

Checks:
- sum(size_level.order_qty) == sku_level.po_qty_total for sized SKUs
- no negative order_qty values
- no duplicate size codes per sku_key (case/format normalized)
- sum(d_size) ~= d_sku within tolerance
- PLAN/REAL separation invariants (po_kind + archived_pos)
- real_pos minimal fields
- portfolio completeness (strict mode)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.sku_normalize import normalize_size
from core.validation.production_readiness import evaluate_production_readiness

DEFAULT_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

FATAL_FALLBACK_NOTES = [
    "NO_DEMAND_ESTIMATE",
    "NO_STOCK_SNAPSHOT",
    "SIZE_MIX_FALLBACK=UNIFORM",
    "SIZE_MIX_FALLBACK=DIM_SKU_SIZE",
    "AVG_PRICE_FALLBACK_DEFAULT",
]

REAL_POS_MIN_FIELDS = ["po_id", "status", "message_date", "units_total", "units_received"]


def _allow_stale_stock_snapshot_for_owner_monitoring(payload: dict) -> bool:
    return (
        str(payload.get("production_scope") or "").upper() == "OWNER_MONITORING_ONLY"
        and payload.get("po_execution_ready") is False
    )


def _normalize_size(size: str | None) -> str:
    if not size:
        return ""
    return str(size).upper().replace(" ", "").replace("-", "")


def _round_half_up_1dp(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _is_kid_sku(sku_key: str) -> bool:
    key = (sku_key or "").upper()
    return "KID" in key or "KIDS" in key


def _is_non_canonical_cl_size(sku_key: str, raw_size: str | None) -> bool:
    if not raw_size:
        return False
    if _is_kid_sku(sku_key):
        return False
    normalized_raw = _normalize_size(raw_size)
    canonical = normalize_size(normalized_raw, product_type="CL")
    if not canonical:
        return True
    if normalized_raw.isdigit() and not canonical.isdigit():
        return True
    return normalized_raw != canonical


def _plan_index(name: str) -> int:
    if not name.startswith("PLAN-"):
        return 0
    try:
        return int(name.split("-", 1)[1])
    except (ValueError, IndexError):
        return 0


def _select_plan(payload: dict) -> tuple[str, dict] | tuple[None, None]:
    pos = payload.get("pos", {})
    if not isinstance(pos, dict) or not pos:
        return None, None

    if "PLAN-1" in pos:
        return "PLAN-1", pos["PLAN-1"]

    active = payload.get("active_pos") or []
    if active:
        name = active[0]
        return name, pos.get(name)

    if "PLAN-0" in pos:
        return "PLAN-0", pos["PLAN-0"]

    plan_name = sorted(pos.keys(), key=_plan_index)[0]
    return plan_name, pos.get(plan_name)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def validate_payload(
    payload: dict,
    db_path: Path | None,
    strict_portfolio: bool = True,
    tolerance: float = 0.01,
) -> list[str]:
    errors: list[str] = []

    pos = payload.get("pos", {})
    if not isinstance(pos, dict) or not pos:
        return ["dashboard output missing pos data"]

    plan_name, plan = _select_plan(payload)
    if not plan_name or not isinstance(plan, dict):
        return [f"plan not found: {plan_name}"]

    sku_level = plan.get("sku_level", [])
    size_level = plan.get("size_level", [])
    plan_po_kind = plan.get("po_kind")

    size_by_sku: dict[str, list[dict]] = {}
    for row in size_level:
        sku_key = row.get("sku_key")
        if not sku_key:
            continue
        size_by_sku.setdefault(sku_key, []).append(row)

    for sku in sku_level:
        sku_key = sku.get("sku_key")
        if not sku_key:
            continue
        is_cl = str(sku_key).startswith("CL_")
        size_rows = size_by_sku.get(sku_key, [])
        sku_total = int(sku.get("po_qty_total", 0) or 0)

        if sku_total < 0:
            errors.append(f"{sku_key}: negative po_qty_total")

        if not size_rows:
            continue

        seen = set()
        for row in size_rows:
            size = _normalize_size(row.get("size"))
            if not size:
                continue
            if size in seen:
                errors.append(f"{sku_key}: duplicate size code {size}")
                break
            seen.add(size)

        size_order_sum = sum(int(r.get("order_qty", 0) or 0) for r in size_rows)
        if size_order_sum != sku_total:
            errors.append(
                f"{sku_key}: size_order_sum={size_order_sum} != po_qty_total={sku_total}"
            )

        for row in size_rows:
            if int(row.get("order_qty", 0) or 0) < 0:
                errors.append(f"{sku_key}: negative size order_qty for {row.get('size')}")
                break
            if int(row.get("order_qty", 0) or 0) > 0:
                try:
                    d_size = float(row.get("d_size", 0) or 0)
                    pre_doc = float(row.get("pre_arr_doc", 0) or 0)
                    post_doc = float(row.get("post_arr_doc", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if d_size > 0 and post_doc <= pre_doc:
                    errors.append(
                        f"{sku_key}: size {row.get('size')} post_arr_doc must exceed pre_arr_doc"
                    )
                    break

        if is_cl:
            for row in size_rows:
                order_qty = int(row.get("order_qty", 0) or 0)
                if order_qty <= 0:
                    continue
                if _is_non_canonical_cl_size(sku_key, row.get("size")):
                    errors.append(
                        f"{sku_key}: non-canonical size {row.get('size')} with order_qty={order_qty}"
                    )
                    break

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

        d_sku = float(sku.get("d_sku", 0) or 0)
        if d_sku > 0:
            d_size_sum = sum(float(r.get("d_size", 0) or 0) for r in size_rows)
            if abs(d_size_sum - d_sku) > tolerance:
                errors.append(
                    f"{sku_key}: sum(d_size)={d_size_sum:.4f} vs d_sku={d_sku:.4f}"
                )
            try:
                pre_doc = float(sku.get("pre_arr_doc", 0) or 0)
                post_doc = float(sku.get("post_arr_doc", 0) or 0)
            except (TypeError, ValueError):
                pre_doc = 0.0
                post_doc = 0.0
            if sku_total > 0 and post_doc <= pre_doc:
                errors.append(
                    f"{sku_key}: post_arr_doc must exceed pre_arr_doc when order_qty > 0"
                )

            try:
                pre_arrival = float(sku.get("pre_arrival", 0) or 0)
            except (TypeError, ValueError):
                pre_arrival = 0.0
            expected_pre = _round_half_up_1dp(pre_arrival / d_sku)
            expected_post = _round_half_up_1dp((pre_arrival + sku_total) / d_sku)
            if abs(pre_doc - expected_pre) > tolerance or abs(post_doc - expected_post) > tolerance:
                errors.append(
                    f"{sku_key}: post_arr_doc formula mismatch (expected {expected_post}, got {post_doc})"
                )

        if plan_po_kind == "REAL_ARCHIVE":
            if "consumption_until_arrival_capped" not in sku:
                errors.append(f"{sku_key}: missing consumption_until_arrival_capped")
            else:
                try:
                    capped = float(sku.get("consumption_until_arrival_capped", 0) or 0)
                    full = float(sku.get("consumption_until_arrival", 0) or 0)
                except (TypeError, ValueError):
                    capped = 0.0
                    full = 0.0
                if capped < -tolerance or capped - full > tolerance:
                    errors.append(
                        f"{sku_key}: invalid consumption_until_arrival_capped={capped} vs consumption_until_arrival={full}"
                    )
            base_dt = sku.get("baseline_snapshot_date")
            msg_dt = sku.get("po_message_date") or plan.get("po_message_date")
            if base_dt and msg_dt and str(base_dt) > str(msg_dt):
                errors.append(
                    f"{sku_key}: baseline_snapshot_date {base_dt} must be <= po_message_date {msg_dt}"
                )

    archived_pos = set(payload.get("archived_pos") or [])
    for po_name, po_data in pos.items():
        if not isinstance(po_data, dict):
            continue
        po_kind = po_data.get("po_kind")
        if po_name.startswith("PLAN-"):
            if po_kind != "PLAN":
                errors.append(f"{po_name}: po_kind must be PLAN")
        else:
            if po_kind != "REAL_ARCHIVE":
                errors.append(f"{po_name}: po_kind must be REAL_ARCHIVE for non-PLAN entry")
            if po_name not in archived_pos:
                errors.append(f"{po_name}: non-PLAN entry missing from archived_pos")
            for sku in po_data.get("sku_level", []) or []:
                sku_key = sku.get("sku_key")
                if not sku_key:
                    continue
                if "consumption_until_arrival_capped" not in sku:
                    errors.append(f"{po_name}/{sku_key}: missing consumption_until_arrival_capped")
            ordered_size_rows = [
                row for row in (po_data.get("size_level", []) or [])
                if int(row.get("order_qty", 0) or 0) > 0
            ]
            has_part_context = any(row.get("po_part_id") for row in ordered_size_rows)
            for size_row in ordered_size_rows:
                qty = int(size_row.get("order_qty", 0) or 0)
                if qty <= 0:
                    continue
                if has_part_context and not size_row.get("po_part_id"):
                    errors.append(
                        f"{po_name}/{size_row.get('sku_key')}/{size_row.get('size')}: missing po_part_id"
                    )

    for idx, row in enumerate(payload.get("real_pos") or []):
        if not isinstance(row, dict):
            errors.append(f"real_pos[{idx}]: invalid entry")
            continue
        missing = []
        for field in REAL_POS_MIN_FIELDS:
            if field not in row:
                missing.append(field)
            elif field != "message_date" and row.get(field) is None:
                missing.append(field)
        if missing:
            errors.append(f"real_pos[{idx}]: missing fields {', '.join(missing)}")

    db_exists = False
    if db_path:
        db_exists = Path(db_path).exists()
        if not db_exists and strict_portfolio:
            errors.append(f"DB path not found: {db_path}")
    if db_path and db_exists:
        try:
            report = evaluate_production_readiness(payload, db_path=db_path)
            for blocker in report.blockers:
                if (
                    "Stock snapshot stale vs cutoff" in blocker
                    and _allow_stale_stock_snapshot_for_owner_monitoring(payload)
                ):
                    continue
                errors.append(f"production_readiness: {blocker}")
        except Exception as exc:
            errors.append(f"production_readiness error: {exc}")

    if strict_portfolio:
        if not db_path or not db_exists:
            errors.append("strict_portfolio requires an existing db_path")
        else:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                if not _table_exists(conn, "portfolio_active"):
                    errors.append("Missing portfolio_active table (strict_portfolio)")
                else:
                    columns = [row[1] for row in conn.execute("PRAGMA table_info(portfolio_active)")]
                    if "active_flag" in columns:
                        rows = conn.execute(
                            "SELECT sku_key FROM portfolio_active WHERE active_flag = 1"
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT sku_key FROM portfolio_active").fetchall()
                    portfolio_skus = {row[0] for row in rows if row[0]}

                    summary_total = (payload.get("summary") or {}).get("total_skus", len(sku_level))
                    if summary_total != len(portfolio_skus):
                        errors.append(
                            f"Portfolio coverage mismatch: dashboard={summary_total} "
                            f"portfolio_active={len(portfolio_skus)}"
                        )

                    dashboard_skus = {sku.get("sku_key") for sku in sku_level if sku.get("sku_key")}
                    missing_from_dashboard = sorted(portfolio_skus - dashboard_skus)
                    if missing_from_dashboard:
                        errors.append(
                            "Portfolio SKUs missing from dashboard: "
                            + ", ".join(missing_from_dashboard[:10])
                            + (" ..." if len(missing_from_dashboard) > 10 else "")
                        )

                    fatal_found = []
                    for sku in sku_level:
                        sku_key = sku.get("sku_key")
                        if not sku_key or sku_key not in portfolio_skus:
                            continue
                        notes = str(sku.get("notes") or "")
                        for token in FATAL_FALLBACK_NOTES:
                            if token in notes:
                                fatal_found.append(f"{sku_key}: {token}")
                                break
                    if fatal_found:
                        errors.append(
                            "Portfolio SKUs with fatal fallback notes: "
                            + ", ".join(fatal_found[:10])
                        )
            finally:
                conn.close()

    return errors


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
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path for strict portfolio checks (default: db/app.db)",
    )
    parser.add_argument(
        "--no-strict-portfolio",
        action="store_true",
        help="Disable strict portfolio checks",
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

    if args.plan:
        pos = payload.get("pos", {})
        if isinstance(pos, dict) and args.plan in pos:
            payload = dict(payload)
            payload["active_pos"] = [args.plan]

    errors = validate_payload(
        payload,
        db_path=args.db,
        strict_portfolio=not args.no_strict_portfolio,
        tolerance=args.tolerance,
    )

    if errors:
        print("INVARIANT FAILURES:")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... {len(errors) - 20} more")
        return 1

    print("OK: dashboard invariants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
