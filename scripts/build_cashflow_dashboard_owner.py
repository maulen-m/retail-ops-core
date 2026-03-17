#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_md(payload: dict[str, Any]) -> str:
    cash = payload["cash_position"]
    calendar = payload["calendar_focus"]
    profit = payload["profit_focus"]
    lines = [
        "# Cashflow Owner Dashboard",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- decision_scope: `{payload['decision_scope']}`",
        "",
        "## Cash Position",
        "",
        f"- base_min_cash_kzt: `{cash.get('base_min_cash_kzt')}`",
        f"- base_min_cash_date: `{cash.get('base_min_cash_date')}`",
        f"- days_to_base_min_cash: `{cash.get('days_to_base_min_cash')}`",
        f"- po_burden_pct_of_base_min_cash: `{cash.get('po_burden_pct_of_base_min_cash')}`",
        "",
        "## Largest PO Commitment",
        "",
        f"- po_id: `{(cash.get('largest_po_commitment') or {}).get('po_id')}`",
        f"- supplier_code: `{(cash.get('largest_po_commitment') or {}).get('supplier_code')}`",
        f"- total_cost_cny: `{(cash.get('largest_po_commitment') or {}).get('total_cost_cny')}`",
        "",
        "## Critical Days",
        "",
    ]
    for row in calendar.get("critical_days", []):
        lines.append(
            f"- `{row.get('date')}` cash_close=`{row.get('cash_close')}` "
            f"driver=`{row.get('primary_driver')}`"
        )
    lines.extend(["", "## Largest Outflow Days", ""])
    largest_outflows = calendar.get("largest_outflow_days", [])
    if not largest_outflows:
        lines.append("- none")
    for row in largest_outflows:
        lines.append(
            f"- `{row.get('date')}` cash_flow_kzt=`{row.get('cash_flow_kzt')}` "
            f"driver=`{row.get('primary_driver')}`"
        )
    lines.extend(["", "## Profit Focus", ""])
    latest_month = profit.get("latest_month") or {}
    lines.extend(
        [
            f"- latest_month: `{latest_month.get('sale_month')}`",
            f"- net_rev_kzt: `{latest_month.get('net_rev_kzt')}`",
            f"- cogs_kzt: `{latest_month.get('cogs_kzt')}`",
            f"- ads_kzt: `{latest_month.get('ads_kzt')}`",
            f"- profit_after_ads_and_opex_kzt: `{latest_month.get('profit_after_ads_and_opex_kzt')}`",
            f"- provisional: `{latest_month.get('provisional')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_cashflow_dashboard_owner(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    cash_risk_path: Path,
    cashflow_calendar_path: Path,
    owner_profit_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    cash_risk = _read_json(cash_risk_path)
    cashflow_calendar = _read_json(cashflow_calendar_path)
    owner_profit = _read_json(owner_profit_path)

    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and str(cash_risk.get("status")) == "PASS"
        and str(cashflow_calendar.get("status")) == "PASS"
        and str(owner_profit.get("status")) == "PASS"
    )

    latest_month = (owner_profit.get("rows") or [])[-1] if (owner_profit.get("rows") or []) else None
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": (
            "PASS_CASHFLOW_OWNER_DASHBOARD_MONITORING_ONLY"
            if ok
            else "FAIL_UPSTREAM_OWNER_SURFACES"
        ),
        "decision_scope": str(owner_profit.get("decision_scope") or "UNKNOWN"),
        "cash_position": {
            "trust_banner": cash_risk.get("trust_banner"),
            "base_min_cash_kzt": cash_risk.get("base_min_cash_kzt"),
            "base_min_cash_date": cash_risk.get("base_min_cash_date"),
            "days_to_base_min_cash": cash_risk.get("days_to_base_min_cash"),
            "po_burden_pct_of_base_min_cash": cash_risk.get("po_burden_pct_of_base_min_cash"),
            "largest_po_commitment": cash_risk.get("largest_po_commitment"),
            "cash_risk_drivers": cash_risk.get("cash_risk_drivers") or [],
        },
        "calendar_focus": {
            "trust_banner": cashflow_calendar.get("trust_banner"),
            "calendar_window": cashflow_calendar.get("calendar_window") or {},
            "critical_days": cashflow_calendar.get("critical_days") or [],
            "largest_outflow_days": cashflow_calendar.get("largest_outflow_days") or [],
            "base_floor_breach_dates": cashflow_calendar.get("base_floor_breach_dates") or [],
            "conservative_floor_breach_dates": cashflow_calendar.get("conservative_floor_breach_dates") or [],
        },
        "profit_focus": {
            "trust_banner": owner_profit.get("trust_banner"),
            "decision_scope": owner_profit.get("decision_scope"),
            "latest_month": latest_month,
        },
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "cash_risk_daily": str(cash_risk_path),
            "cashflow_calendar_daily": str(cashflow_calendar_path),
            "owner_profit_daily": str(owner_profit_path),
        },
    }

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cashflow_dashboard_owner.json"
    md_path = out_dir / "cashflow_dashboard_owner.md"
    _write_json(json_path, payload)
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build owner cashflow dashboard from existing owner surfaces.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--cash-risk", type=Path, required=True)
    parser.add_argument("--cashflow-calendar", type=Path, required=True)
    parser.add_argument("--owner-profit", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    args = parser.parse_args()
    payload = build_cashflow_dashboard_owner(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        cash_risk_path=args.cash_risk,
        cashflow_calendar_path=args.cashflow_calendar,
        owner_profit_path=args.owner_profit,
        output_root=args.output_root,
    )
    out_dir = args.output_root / args.as_of
    print(f"cashflow_dashboard_owner_json={(out_dir / 'cashflow_dashboard_owner.json').resolve()}")
    print(f"cashflow_dashboard_owner_md={(out_dir / 'cashflow_dashboard_owner.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
