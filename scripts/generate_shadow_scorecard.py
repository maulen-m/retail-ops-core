#!/usr/bin/env python3
"""
Shadow Mode Scorecard Generator

Part 4 requirement: Generate daily scorecard for shadow mode operations.
Outputs CSV with decision breakdown without executing any POs.

Scorecard includes:
- Total proposed spend (KZT)
- ORDER_FULL / ORDER_WITH_FLAG / REVIEW_REQUIRED counts
- Top 10 SKUs by spend
- Blocked spend by reason
- Override count and top overridden SKUs
- Fallback-demand count

Usage:
    python scripts/generate_shadow_scorecard.py

Output:
    exports/shadow_scorecard_YYYY-MM-DD.csv
"""

import sqlite3
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Any
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import get_cutoff_date_almaty
from core.config.business_params import get_fx_rates, get_demand_overrides
from core.calc.demand_estimator import DemandEstimator, DemandEstimatorConfig
from core.capital.guardrails import (
    check_sku_guardrails,
    check_all_guardrails,
    check_fallback_usage,
    get_budget_caps,
    ROICAction,
)
from core.tracking.run_tracker import RunTracker
from core.alerts.error_alerts import send_run_success_alert, send_run_failure_alert

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"
DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


@dataclass
class ScorecardSKU:
    """SKU-level scorecard entry."""
    sku_key: str
    po_qty: int
    po_value_kzt: float
    roic_pct: float
    roic_action: str  # ORDER_FULL, ORDER_WITH_FLAG, REVIEW_REQUIRED
    guardrail_status: str  # PASS, WARN, BLOCK
    blocked_reason: str
    override_applied: bool
    override_value: Optional[float]
    demand_fallback: bool  # True if no estimate available


@dataclass
class ScorecardSummary:
    """Summary statistics for scorecard."""
    scorecard_date: str
    total_skus: int
    total_po_value_kzt: float
    order_full_count: int
    order_full_value_kzt: float
    order_with_flag_count: int
    order_with_flag_value_kzt: float
    review_required_count: int
    review_required_value_kzt: float
    blocked_by_roic_count: int
    blocked_by_roic_value_kzt: float
    blocked_by_concentration_count: int
    blocked_by_concentration_value_kzt: float
    blocked_by_budget_count: int
    blocked_by_budget_value_kzt: float
    blocked_by_missing_count: int
    blocked_by_missing_value_kzt: float
    override_count: int
    fallback_demand_count: int
    source: str = ""


def _load_dashboard_po(po_name: Optional[str] = None) -> Tuple[str, dict[str, Any]] | None:
    if not DASHBOARD_PATH.exists():
        return None
    try:
        data = json.loads(DASHBOARD_PATH.read_text())
    except Exception:
        return None

    pos = data.get("pos", {})
    if not isinstance(pos, dict) or not pos:
        return None

    if not po_name:
        active = data.get("active_pos") or []
        if active:
            po_name = active[0]
        elif "PO-5" in pos:
            po_name = "PO-5"
        else:
            po_name = sorted(pos.keys())[0]

    po_data = pos.get(po_name)
    if not isinstance(po_data, dict):
        return None

    return po_name, po_data


def _parse_override(notes: str) -> tuple[bool, Optional[float]]:
    if not notes:
        return False, None
    if "D_OVERRIDE=" in notes:
        try:
            value = float(notes.split("D_OVERRIDE=")[1].split(",")[0].strip())
        except Exception:
            value = None
        return True, value
    return False, None


def get_active_skus(db_path: Path) -> list[dict]:
    """Get active SKUs with costs and demand data."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            s.sku_key,
            s.model as product_name,
            s.base_cost_cny,
            s.weight_kg as weight_per_unit_kg,
            s.product_type,
            m.d30 as d_legacy,
            m.roic_monthly,
            de.d_final,
            de.d_final_with_override,
            de.override_applied,
            de.override_value
        FROM dim_sku s
        LEFT JOIN fact_sku_metrics m ON s.sku_key = m.sku_key
        LEFT JOIN fact_demand_estimates de ON s.sku_key = de.sku_key
        WHERE s.active_flag = 1
          AND s.base_cost_cny > 0
    """).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_current_inventory(db_path: Path) -> dict[str, int]:
    """Get current inventory by SKU."""
    conn = sqlite3.connect(str(db_path))

    rows = conn.execute("""
        SELECT sku_key, SUM(current_stock) as stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size)
        GROUP BY sku_key
    """).fetchall()

    conn.close()
    return {row[0]: row[1] for row in rows}


def calculate_po_recommendations(db_path: Path) -> tuple[list[ScorecardSKU], ScorecardSummary]:
    """Calculate PO recommendations for all active SKUs."""
    from core.config.inventory_params import get_params

    params = get_params()
    fx_rates = get_fx_rates().to_dict()
    overrides = get_demand_overrides()

    cny_kzt = fx_rates.get("cny_kzt", 78)
    usd_kzt = fx_rates.get("usd_kzt", 530)
    dlv_rate = fx_rates.get("dlv_rate_usd_kg", 2.66)

    L = params.L
    R = params.R
    B = params.B
    z = params.z
    TV = params.TV

    dashboard_po = _load_dashboard_po()
    if dashboard_po:
        po_name, po_data = dashboard_po
        sku_rows = po_data.get("sku_level", [])
        scorecard_skus: list[ScorecardSKU] = []

        order_full = {"count": 0, "value": 0.0}
        order_with_flag = {"count": 0, "value": 0.0}
        review_required = {"count": 0, "value": 0.0}
        blocked_roic = {"count": 0, "value": 0.0}
        blocked_concentration = {"count": 0, "value": 0.0}
        blocked_budget = {"count": 0, "value": 0.0}
        blocked_missing = {"count": 0, "value": 0.0}
        override_count = 0
        fallback_count = 0

        proposed_po: dict[str, int] = {}
        unit_costs: dict[str, float] = {}

        for row in sku_rows:
            sku_key = row.get("sku_key") or ""
            if not sku_key:
                continue
            po_qty = int(row.get("po_qty_total") or 0)
            po_value_kzt = float(row.get("po_cogs_kzt") or 0.0)
            roic_pct = float(row.get("roic_pct") or 0.0)
            roic = roic_pct / 100.0
            unit_cost_kzt = float(row.get("unit_cogs") or 0.0)
            unit_costs[sku_key] = unit_cost_kzt
            proposed_po[sku_key] = po_qty

            notes = row.get("notes") or ""
            override_applied, override_value = _parse_override(notes)
            if override_applied:
                override_count += 1
            demand_fallback = "NO_DEMAND_ESTIMATE" in notes
            if demand_fallback:
                fallback_count += 1

            if po_qty > 0:
                if roic >= 0.20:
                    roic_action = "ORDER_FULL"
                    order_full["count"] += 1
                    order_full["value"] += po_value_kzt
                elif roic >= 0.10:
                    roic_action = "ORDER_WITH_FLAG"
                    order_with_flag["count"] += 1
                    order_with_flag["value"] += po_value_kzt
                else:
                    roic_action = "REVIEW_REQUIRED"
                    review_required["count"] += 1
                    review_required["value"] += po_value_kzt
            else:
                roic_action = "REVIEW_REQUIRED"

            guardrail_result = check_sku_guardrails(
                sku_key=sku_key,
                roic=roic,
                order_qty=po_qty,
                po_value_kzt=po_value_kzt,
                unit_cost_kzt=unit_cost_kzt,
            )

            blocked_reason = ""
            if not guardrail_result.approved:
                blocked_reason = "; ".join(guardrail_result.blockers)
                if "ROIC" in blocked_reason or "roic" in blocked_reason.lower():
                    blocked_roic["count"] += 1
                    blocked_roic["value"] += po_value_kzt
                elif "concentration" in blocked_reason.lower():
                    blocked_concentration["count"] += 1
                    blocked_concentration["value"] += po_value_kzt
                elif "budget" in blocked_reason.lower():
                    blocked_budget["count"] += 1
                    blocked_budget["value"] += po_value_kzt
                elif "missing" in blocked_reason.lower() or "unit_costs" in blocked_reason:
                    blocked_missing["count"] += 1
                    blocked_missing["value"] += po_value_kzt

            scorecard_skus.append(ScorecardSKU(
                sku_key=sku_key,
                po_qty=po_qty,
                po_value_kzt=po_value_kzt,
                roic_pct=roic_pct,
                roic_action=roic_action,
                guardrail_status=guardrail_result.guardrail_status,
                blocked_reason=blocked_reason,
                override_applied=override_applied,
                override_value=override_value,
                demand_fallback=demand_fallback,
            ))

        total_po_value = sum(s.po_value_kzt for s in scorecard_skus if s.po_qty > 0)
        summary = ScorecardSummary(
            scorecard_date=date.today().isoformat(),
            total_skus=len([s for s in scorecard_skus if s.po_qty > 0]),
            total_po_value_kzt=total_po_value,
            order_full_count=order_full["count"],
            order_full_value_kzt=order_full["value"],
            order_with_flag_count=order_with_flag["count"],
            order_with_flag_value_kzt=order_with_flag["value"],
            review_required_count=review_required["count"],
            review_required_value_kzt=review_required["value"],
            blocked_by_roic_count=blocked_roic["count"],
            blocked_by_roic_value_kzt=blocked_roic["value"],
            blocked_by_concentration_count=blocked_concentration["count"],
            blocked_by_concentration_value_kzt=blocked_concentration["value"],
            blocked_by_budget_count=blocked_budget["count"],
            blocked_by_budget_value_kzt=blocked_budget["value"],
            blocked_by_missing_count=blocked_missing["count"],
            blocked_by_missing_value_kzt=blocked_missing["value"],
            override_count=override_count,
            fallback_demand_count=fallback_count,
            source=f"dashboard:{po_name}",
        )

        return scorecard_skus, summary

    skus = get_active_skus(db_path)
    inventory = get_current_inventory(db_path)

    scorecard_skus: list[ScorecardSKU] = []

    # Tracking counters
    order_full = {"count": 0, "value": 0.0}
    order_with_flag = {"count": 0, "value": 0.0}
    review_required = {"count": 0, "value": 0.0}
    blocked_roic = {"count": 0, "value": 0.0}
    blocked_concentration = {"count": 0, "value": 0.0}
    blocked_budget = {"count": 0, "value": 0.0}
    blocked_missing = {"count": 0, "value": 0.0}
    override_count = 0
    fallback_count = 0

    # Build proposed PO and costs for concentration check
    proposed_po: dict[str, int] = {}
    unit_costs: dict[str, float] = {}

    for sku in skus:
        sku_key = sku["sku_key"]
        base_cost_cny = sku.get("base_cost_cny") or 0
        weight_kg = sku.get("weight_per_unit_kg") or 0.3

        # Calculate unit COGS
        unit_cogs = (base_cost_cny * cny_kzt) + (weight_kg * dlv_rate * usd_kzt)
        unit_costs[sku_key] = unit_cogs

        # Get demand (prioritize override, then d_final, then legacy)
        d_final_override = sku.get("d_final_with_override")
        d_final = sku.get("d_final")
        d_legacy = sku.get("d_legacy") or 0

        demand_fallback = False
        if d_final_override is not None:
            d = d_final_override
        elif d_final is not None:
            d = d_final
        else:
            d = d_legacy
            if d_legacy == 0:
                demand_fallback = True
                fallback_count += 1

        # Check if override was applied
        override_applied = bool(sku.get("override_applied"))
        override_value = sku.get("override_value") if override_applied else None
        if override_applied:
            override_count += 1

        # Calculate reorder point and order qty
        stock = inventory.get(sku_key, 0)
        sigma = d * 0.5  # Simple sigma estimate
        ss = z * sigma * (L ** 0.5) * (1 + TV)
        rop = (d * L) + ss

        if stock < rop:
            target = d * (L + R + B)
            order_qty = max(0, int(target - stock))
        else:
            order_qty = 0

        proposed_po[sku_key] = order_qty

        # Calculate ROIC
        if unit_cogs > 0 and d > 0:
            profit_margin = 0.30  # Assume 30% margin for estimation
            unit_profit = unit_cogs * profit_margin / (1 - profit_margin)
            monthly_profit = unit_profit * d * 30
            k_avg = d * (L + R/2) * unit_cogs + ss * unit_cogs
            roic = monthly_profit / k_avg if k_avg > 0 else 0
        else:
            roic = 0

        # Determine ROIC action
        if roic >= 0.20:
            roic_action = "ORDER_FULL"
            order_full["count"] += 1
            order_full["value"] += order_qty * unit_cogs
        elif roic >= 0.10:
            roic_action = "ORDER_WITH_FLAG"
            order_with_flag["count"] += 1
            order_with_flag["value"] += order_qty * unit_cogs
        else:
            roic_action = "REVIEW_REQUIRED"
            review_required["count"] += 1
            review_required["value"] += order_qty * unit_cogs

        # Check guardrails
        guardrail_result = check_sku_guardrails(
            sku_key=sku_key,
            roic=roic,
            order_qty=order_qty
        )

        blocked_reason = ""
        if not guardrail_result.approved:
            blocked_reason = "; ".join(guardrail_result.blockers)

            # Categorize block reason
            if "ROIC" in blocked_reason or "roic" in blocked_reason.lower():
                blocked_roic["count"] += 1
                blocked_roic["value"] += order_qty * unit_cogs
            elif "concentration" in blocked_reason.lower():
                blocked_concentration["count"] += 1
                blocked_concentration["value"] += order_qty * unit_cogs
            elif "budget" in blocked_reason.lower():
                blocked_budget["count"] += 1
                blocked_budget["value"] += order_qty * unit_cogs
            elif "missing" in blocked_reason.lower() or "unit_costs" in blocked_reason:
                blocked_missing["count"] += 1
                blocked_missing["value"] += order_qty * unit_cogs

        scorecard_skus.append(ScorecardSKU(
            sku_key=sku_key,
            po_qty=order_qty,
            po_value_kzt=order_qty * unit_cogs,
            roic_pct=roic * 100,
            roic_action=roic_action,
            guardrail_status=guardrail_result.guardrail_status,
            blocked_reason=blocked_reason,
            override_applied=override_applied,
            override_value=override_value,
            demand_fallback=demand_fallback
        ))

    # Calculate total PO value
    total_po_value = sum(s.po_value_kzt for s in scorecard_skus if s.po_qty > 0)

    # Create summary
    summary = ScorecardSummary(
        scorecard_date=date.today().isoformat(),
        total_skus=len([s for s in scorecard_skus if s.po_qty > 0]),
        total_po_value_kzt=total_po_value,
        order_full_count=order_full["count"],
        order_full_value_kzt=order_full["value"],
        order_with_flag_count=order_with_flag["count"],
        order_with_flag_value_kzt=order_with_flag["value"],
        review_required_count=review_required["count"],
        review_required_value_kzt=review_required["value"],
        blocked_by_roic_count=blocked_roic["count"],
        blocked_by_roic_value_kzt=blocked_roic["value"],
        blocked_by_concentration_count=blocked_concentration["count"],
        blocked_by_concentration_value_kzt=blocked_concentration["value"],
        blocked_by_budget_count=blocked_budget["count"],
        blocked_by_budget_value_kzt=blocked_budget["value"],
        blocked_by_missing_count=blocked_missing["count"],
        blocked_by_missing_value_kzt=blocked_missing["value"],
        override_count=override_count,
        fallback_demand_count=fallback_count,
        source="db:computed",
    )

    return scorecard_skus, summary


def write_scorecard_csv(
    scorecard_skus: list[ScorecardSKU],
    summary: ScorecardSummary,
    output_dir: Path
) -> Path:
    """Write scorecard to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = date.today().isoformat()

    # Write summary CSV
    summary_path = output_dir / f"shadow_scorecard_{today_str}.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Summary header
        writer.writerow(["SHADOW MODE SCORECARD", today_str])
        writer.writerow([])

        # Summary statistics
        if summary.source:
            writer.writerow(["Source", summary.source])
            writer.writerow([])

        writer.writerow(["Metric", "Count", "Value (KZT)"])
        writer.writerow(["Total SKUs with Orders", summary.total_skus, f"{summary.total_po_value_kzt:,.0f}"])
        writer.writerow([])

        writer.writerow(["ROIC BREAKDOWN"])
        writer.writerow(["ORDER_FULL (>=20%)", summary.order_full_count, f"{summary.order_full_value_kzt:,.0f}"])
        writer.writerow(["ORDER_WITH_FLAG (10-20%)", summary.order_with_flag_count, f"{summary.order_with_flag_value_kzt:,.0f}"])
        writer.writerow(["REVIEW_REQUIRED (<10%)", summary.review_required_count, f"{summary.review_required_value_kzt:,.0f}"])
        writer.writerow([])

        writer.writerow(["BLOCKED SPEND BY REASON"])
        writer.writerow(["Blocked by ROIC", summary.blocked_by_roic_count, f"{summary.blocked_by_roic_value_kzt:,.0f}"])
        writer.writerow(["Blocked by Concentration", summary.blocked_by_concentration_count, f"{summary.blocked_by_concentration_value_kzt:,.0f}"])
        writer.writerow(["Blocked by Budget", summary.blocked_by_budget_count, f"{summary.blocked_by_budget_value_kzt:,.0f}"])
        writer.writerow(["Blocked by Missing Inputs", summary.blocked_by_missing_count, f"{summary.blocked_by_missing_value_kzt:,.0f}"])
        writer.writerow([])

        writer.writerow(["OVERRIDES & FALLBACKS"])
        writer.writerow(["Demand Overrides Applied", summary.override_count, ""])
        writer.writerow(["Fallback Demand (No Estimate)", summary.fallback_demand_count, ""])
        writer.writerow([])

        # Top 10 SKUs by spend
        writer.writerow(["TOP 10 SKUs BY SPEND"])
        writer.writerow(["SKU", "Order Qty", "Value (KZT)", "ROIC %", "Action", "Status"])
        top_10 = sorted(scorecard_skus, key=lambda x: x.po_value_kzt, reverse=True)[:10]
        for sku in top_10:
            writer.writerow([
                sku.sku_key,
                sku.po_qty,
                f"{sku.po_value_kzt:,.0f}",
                f"{sku.roic_pct:.1f}%",
                sku.roic_action,
                sku.guardrail_status
            ])
        writer.writerow([])

        # Top overridden SKUs
        overridden = [s for s in scorecard_skus if s.override_applied]
        if overridden:
            writer.writerow(["TOP OVERRIDDEN SKUs"])
            writer.writerow(["SKU", "Override Value", "Order Qty", "Value (KZT)"])
            for sku in sorted(overridden, key=lambda x: x.po_value_kzt, reverse=True)[:5]:
                writer.writerow([
                    sku.sku_key,
                    f"{sku.override_value:.2f}" if sku.override_value else "",
                    sku.po_qty,
                    f"{sku.po_value_kzt:,.0f}"
                ])

    # Write detailed SKU list
    detail_path = output_dir / f"shadow_scorecard_detail_{today_str}.csv"
    with open(detail_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sku_key", "po_qty", "po_value_kzt", "roic_pct", "roic_action",
            "guardrail_status", "blocked_reason", "override_applied",
            "override_value", "demand_fallback"
        ])
        for sku in scorecard_skus:
            writer.writerow([
                sku.sku_key,
                sku.po_qty,
                f"{sku.po_value_kzt:.0f}",
                f"{sku.roic_pct:.1f}",
                sku.roic_action,
                sku.guardrail_status,
                sku.blocked_reason,
                sku.override_applied,
                sku.override_value or "",
                sku.demand_fallback
            ])

    return summary_path


def format_telegram_digest(summary: ScorecardSummary) -> str:
    """Format summary for Telegram alert."""
    source_line = f"\n<b>Source:</b> {summary.source}" if summary.source else ""
    return f"""<b>Shadow Mode Scorecard - {summary.scorecard_date}</b>{source_line}

<b>Total Proposed Spend:</b> {summary.total_po_value_kzt:,.0f} KZT
<b>SKUs with Orders:</b> {summary.total_skus}

<b>ROIC Breakdown:</b>
  • ORDER_FULL (≥20%): {summary.order_full_count} ({summary.order_full_value_kzt:,.0f} KZT)
  • ORDER_WITH_FLAG: {summary.order_with_flag_count} ({summary.order_with_flag_value_kzt:,.0f} KZT)
  • REVIEW_REQUIRED: {summary.review_required_count} ({summary.review_required_value_kzt:,.0f} KZT)

<b>Blocked:</b> {summary.blocked_by_roic_count + summary.blocked_by_concentration_count + summary.blocked_by_budget_count + summary.blocked_by_missing_count} SKUs
<b>Overrides:</b> {summary.override_count} | <b>Fallbacks:</b> {summary.fallback_demand_count}"""


def main():
    """Generate shadow scorecard."""
    print(f"Generating Shadow Mode Scorecard for {date.today().isoformat()}")
    print("=" * 60)

    with RunTracker("SHADOW_SCORECARD", DB_PATH) as tracker:
        try:
            tracker.start_step("calculate_recommendations")
            scorecard_skus, summary = calculate_po_recommendations(DB_PATH)
            tracker.complete_step(records=len(scorecard_skus))

            tracker.start_step("write_csv")
            output_path = write_scorecard_csv(scorecard_skus, summary, EXPORTS_DIR)
            tracker.add_output_file(str(output_path))
            tracker.complete_step()

            tracker.set_metrics(
                skus_processed=summary.total_skus,
                overrides_applied=summary.override_count
            )

            # Print summary
            print(f"\nSummary:")
            if summary.source:
                print(f"  Source: {summary.source}")
            print(f"  Total SKUs with Orders: {summary.total_skus}")
            print(f"  Total Proposed Spend: {summary.total_po_value_kzt:,.0f} KZT")
            print()
            print(f"  ORDER_FULL (≥20%): {summary.order_full_count} ({summary.order_full_value_kzt:,.0f} KZT)")
            print(f"  ORDER_WITH_FLAG (10-20%): {summary.order_with_flag_count} ({summary.order_with_flag_value_kzt:,.0f} KZT)")
            print(f"  REVIEW_REQUIRED (<10%): {summary.review_required_count} ({summary.review_required_value_kzt:,.0f} KZT)")
            print()
            print(f"  Blocked by ROIC: {summary.blocked_by_roic_count}")
            print(f"  Blocked by Concentration: {summary.blocked_by_concentration_count}")
            print(f"  Blocked by Budget: {summary.blocked_by_budget_count}")
            print(f"  Blocked by Missing: {summary.blocked_by_missing_count}")
            print()
            print(f"  Overrides Applied: {summary.override_count}")
            print(f"  Fallback Demand: {summary.fallback_demand_count}")
            print()
            print(f"Output: {output_path}")

            # Send Telegram digest
            tracker.start_step("send_telegram_digest")
            telegram_msg = format_telegram_digest(summary)
            try:
                from core.alerts.error_alerts import send_success_alert
                send_success_alert(telegram_msg, "shadow_scorecard")
                tracker.complete_step()
            except Exception as e:
                print(f"  Warning: Failed to send Telegram: {e}")
                tracker.fail_step(str(e))

        except Exception as e:
            print(f"ERROR: {e}")
            tracker.fail_step(str(e))
            raise


if __name__ == "__main__":
    main()
