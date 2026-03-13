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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _latest_profit_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: str(row.get("sale_month") or ""))[-1]


def _build_headline(
    *,
    profit: dict[str, Any],
    cash: dict[str, Any],
    cashflow_calendar: dict[str, Any],
    po_sku: dict[str, Any],
) -> str:
    latest_month = profit.get("latest_month") or {}
    top_capital = ((po_sku.get("action_buckets") or {}).get("tied_up_capital") or [])
    freeze_rows = ((po_sku.get("action_buckets") or {}).get("freeze_or_kill_review") or [])
    planning_snapshot = po_sku.get("planning_snapshot") or {}
    parts: list[str] = []
    if latest_month.get("sale_month"):
        parts.append(
            f"Latest monitored month {latest_month.get('sale_month')} shows "
            f"{latest_month.get('profit_after_ads_and_opex_kzt')} KZT after ads and OPEX."
        )
    if cash.get("base_min_cash_date"):
        parts.append(
            f"Lowest modeled cash point is {cash.get('base_min_cash_kzt')} KZT on {cash.get('base_min_cash_date')}."
        )
    critical_days = cashflow_calendar.get("critical_days") or []
    if critical_days:
        first_critical = critical_days[0]
        parts.append(
            f"Cashflow calendar flags {first_critical.get('date')} as a critical day driven by {first_critical.get('primary_driver')}."
        )
    if top_capital:
        top = top_capital[0]
        parts.append(f"Biggest PO capital tie-up is {top.get('sku_key')} at {top.get('po_cogs_kzt')} KZT.")
    if freeze_rows:
        parts.append(f"Immediate freeze/kill review candidate is {freeze_rows[0].get('sku_key')}.")
    if planning_snapshot.get("freshness") == "STALE_VS_CUTOFF":
        parts.append(
            f"PO planning snapshot is stale by {planning_snapshot.get('staleness_days_vs_cutoff')} days versus cutoff."
        )
    return " ".join(parts)


def _build_owner_actions(
    *,
    cash: dict[str, Any],
    cashflow_calendar: dict[str, Any],
    po_sku: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if cash.get("days_to_base_min_cash") is not None:
        actions.append(
            f"Monitor cash runway into {cash.get('base_min_cash_date')} "
            f"({cash.get('days_to_base_min_cash')} days)."
        )
    critical_days = cashflow_calendar.get("critical_days") or []
    if critical_days:
        row = critical_days[0]
        actions.append(
            f"Prepare for {row.get('primary_driver')} pressure on {row.get('date')} with modeled cash close {row.get('cash_close')} KZT."
        )
    reorder_rows = ((po_sku.get("action_buckets") or {}).get("reorder_now") or [])
    if reorder_rows:
        row = reorder_rows[0]
        actions.append(
            f"Prioritize reorder review for {row.get('sku_key')} with deficit {row.get('deficit_total')} "
            f"and PO cogs {row.get('po_cogs_kzt')} KZT."
        )
    freeze_rows = ((po_sku.get("action_buckets") or {}).get("freeze_or_kill_review") or [])
    if freeze_rows:
        row = freeze_rows[0]
        actions.append(
            f"Review freeze/kill decision for {row.get('sku_key')} because ROIC is {row.get('roic_pct')}% "
            f"and monthly profit is {row.get('monthly_profit')} KZT."
        )
    return actions


def _capital_summary(po_sku: dict[str, Any]) -> dict[str, Any]:
    capital_radar = po_sku.get("capital_radar") or {}
    tied_rows = ((po_sku.get("action_buckets") or {}).get("tied_up_capital") or [])
    freeze_rows = ((po_sku.get("action_buckets") or {}).get("freeze_or_kill_review") or [])
    reorder_rows = ((po_sku.get("action_buckets") or {}).get("reorder_now") or [])
    largest = capital_radar.get("largest_tied_up_sku")
    if not largest and tied_rows:
        largest = tied_rows[0]
    tied_top5 = capital_radar.get("tied_up_capital_top5_kzt")
    if tied_top5 is None:
        tied_top5 = round(sum(float(row.get("po_cogs_kzt") or 0.0) for row in tied_rows), 2)
    freeze_cogs = capital_radar.get("freeze_or_kill_cogs_kzt")
    if freeze_cogs is None:
        freeze_cogs = round(sum(float(row.get("po_cogs_kzt") or 0.0) for row in freeze_rows), 2)
    reorder_cogs = capital_radar.get("reorder_now_cogs_kzt")
    if reorder_cogs is None:
        reorder_cogs = round(sum(float(row.get("po_cogs_kzt") or 0.0) for row in reorder_rows), 2)
    return {
        "largest_tied_up_sku": largest,
        "tied_up_capital_top5_kzt": tied_top5,
        "freeze_or_kill_cogs_kzt": freeze_cogs,
        "reorder_now_cogs_kzt": reorder_cogs,
    }


def _render_md(payload: dict[str, Any]) -> str:
    profit = payload["sections"]["profit"]
    cash = payload["sections"]["cash_risk"]
    cashflow_calendar = payload["sections"]["cashflow_calendar"]
    po_sku = payload["sections"]["po_sku"]
    capital_summary = _capital_summary(po_sku)
    latest_month = profit.get("latest_month") or {}
    lines = [
        "# Owner Daily Brief",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        "",
        "## What Matters Now",
        "",
        payload["headline"],
        "",
        "## Profit",
        "",
        f"- trust_banner: `{profit['trust_banner']}`",
        f"- production_acceptable: `{str(bool(profit['production_acceptable'])).lower()}`",
        f"- decision_scope: `{profit['decision_scope']}`",
        f"- latest_sale_month: `{latest_month.get('sale_month')}`",
        f"- latest_net_rev_kzt: `{latest_month.get('net_rev_kzt')}`",
        f"- latest_profit_after_ads_kzt: `{latest_month.get('profit_after_ads_kzt')}`",
        f"- latest_profit_after_ads_and_opex_kzt: `{latest_month.get('profit_after_ads_and_opex_kzt')}`",
        "",
        "## Cash Risk",
        "",
        f"- trust_banner: `{cash['trust_banner']}`",
        f"- base_min_cash_kzt: `{cash['base_min_cash_kzt']}`",
        f"- conservative_min_cash_kzt: `{cash['conservative_min_cash_kzt']}`",
        f"- po_total_cogs_kzt: `{cash['po_total_cogs_kzt']}`",
        f"- real_pos_count: `{cash['real_pos_count']}`",
        "",
        "## Cashflow Calendar",
        "",
        f"- trust_banner: `{cashflow_calendar['trust_banner']}`",
        f"- start_date: `{cashflow_calendar['calendar_window'].get('start_date')}`",
        f"- end_date: `{cashflow_calendar['calendar_window'].get('end_date')}`",
        f"- base_floor_breach_dates: `{cashflow_calendar.get('base_floor_breach_dates')}`",
        "",
        "## PO / SKU",
        "",
        f"- trust_banner: `{po_sku['trust_banner']}`",
        f"- total_skus: `{po_sku['summary'].get('total_skus')}`",
        f"- total_units: `{po_sku['summary'].get('total_units')}`",
        f"- total_po_cogs_kzt: `{po_sku['summary'].get('total_po_cogs_kzt')}`",
        f"- largest_tied_up_sku: `{(capital_summary.get('largest_tied_up_sku') or {}).get('sku_key')}`",
        f"- tied_up_capital_top5_kzt: `{capital_summary.get('tied_up_capital_top5_kzt')}`",
        "",
        "## Owner Actions",
        "",
    ]
    for action in payload["owner_actions"]:
        lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Top PO Exposure",
            "",
        "| PO ID | Supplier | Units | Cost CNY |",
        "|---|---|---:|---:|",
        ]
    )
    for row in po_sku["top_real_pos"]:
        lines.append(
            f"| `{row.get('po_id')}` | `{row.get('supplier_code')}` | {row.get('units_total')} | {row.get('total_cost_cny')} |"
        )
    return "\n".join(lines) + "\n"


def build_owner_daily_brief(
    *,
    as_of: str,
    owner_profit_path: Path,
    cash_risk_path: Path,
    cashflow_calendar_path: Path,
    po_sku_path: Path,
    output_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    owner_profit = _read_json(owner_profit_path)
    cash_risk = _read_json(cash_risk_path)
    cashflow_calendar = _read_json(cashflow_calendar_path)
    po_sku = _read_json(po_sku_path)

    profit_ok = str(owner_profit.get("status")) == "PASS" and bool(owner_profit.get("production_acceptable"))
    cash_ok = str(cash_risk.get("status")) == "PASS"
    cashflow_ok = str(cashflow_calendar.get("status")) == "PASS"
    po_ok = str(po_sku.get("status")) == "PASS"
    ok = profit_ok and cash_ok and cashflow_ok and po_ok

    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_OWNER_DAILY_BRIEF_READY" if ok else "FAIL_OWNER_DAILY_BRIEF_BLOCKED",
        "sections": {
            "profit": {
                "trust_banner": owner_profit.get("trust_banner"),
                "production_acceptable": bool(owner_profit.get("production_acceptable")),
                "decision_scope": owner_profit.get("decision_scope"),
                "latest_month": _latest_profit_row(owner_profit.get("rows") or []),
                "rows": owner_profit.get("rows") or [],
                "source_path": str(owner_profit_path),
            },
            "cash_risk": {
                "trust_banner": cash_risk.get("trust_banner"),
                "base_min_cash_kzt": cash_risk.get("base_min_cash_kzt"),
                "base_min_cash_date": cash_risk.get("base_min_cash_date"),
                "conservative_min_cash_kzt": cash_risk.get("conservative_min_cash_kzt"),
                "conservative_min_cash_date": cash_risk.get("conservative_min_cash_date"),
                "po_total_cogs_kzt": cash_risk.get("po_total_cogs_kzt"),
                "real_pos_count": cash_risk.get("real_pos_count"),
                "days_to_base_min_cash": cash_risk.get("days_to_base_min_cash"),
                "cash_risk_drivers": cash_risk.get("cash_risk_drivers") or [],
                "source_path": str(cash_risk_path),
            },
            "cashflow_calendar": {
                "trust_banner": cashflow_calendar.get("trust_banner"),
                "calendar_window": cashflow_calendar.get("calendar_window") or {},
                "critical_days": cashflow_calendar.get("critical_days") or [],
                "largest_outflow_days": cashflow_calendar.get("largest_outflow_days") or [],
                "base_floor_breach_dates": cashflow_calendar.get("base_floor_breach_dates") or [],
                "conservative_floor_breach_dates": cashflow_calendar.get("conservative_floor_breach_dates") or [],
                "source_path": str(cashflow_calendar_path),
            },
            "po_sku": {
                "trust_banner": po_sku.get("trust_banner"),
                "summary": po_sku.get("summary") or {},
                "top_real_pos": po_sku.get("top_real_pos") or [],
                "planning_snapshot": po_sku.get("planning_snapshot") or {},
                "action_buckets": po_sku.get("action_buckets") or {},
                "capital_radar": po_sku.get("capital_radar") or {},
                "source_path": str(po_sku_path),
            },
        },
    }
    payload["headline"] = _build_headline(
        profit=payload["sections"]["profit"],
        cash=payload["sections"]["cash_risk"],
        cashflow_calendar=payload["sections"]["cashflow_calendar"],
        po_sku=payload["sections"]["po_sku"],
    )
    payload["owner_actions"] = _build_owner_actions(
        cash=payload["sections"]["cash_risk"],
        cashflow_calendar=payload["sections"]["cashflow_calendar"],
        po_sku=payload["sections"]["po_sku"],
    )

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "owner_daily_brief.json"
    md_path = out_dir / "owner_daily_brief.md"
    _write_json(json_path, payload)
    md_path.write_text(_render_md(payload), encoding="utf-8")
    _write_json(
        validation_root / as_of / "trust_report.json",
        {
            "generated_at": _now_utc(),
            "status": payload["status"],
            "trust_banner": payload["trust_banner"],
            "json_path": str(json_path.resolve()),
            "md_path": str(md_path.resolve()),
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build combined owner daily brief.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-profit", type=Path, required=True)
    parser.add_argument("--cash-risk", type=Path, required=True)
    parser.add_argument("--cashflow-calendar", type=Path, required=True)
    parser.add_argument("--po-sku", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/owner_daily_brief"))
    args = parser.parse_args()
    payload = build_owner_daily_brief(
        as_of=args.as_of,
        owner_profit_path=args.owner_profit,
        cash_risk_path=args.cash_risk,
        cashflow_calendar_path=args.cashflow_calendar,
        po_sku_path=args.po_sku,
        output_root=args.output_root,
        validation_root=args.validation_root,
    )
    print(f"owner_daily_brief_json={(args.output_root / args.as_of / 'owner_daily_brief.json').resolve()}")
    print(f"owner_daily_brief_md={(args.output_root / args.as_of / 'owner_daily_brief.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
