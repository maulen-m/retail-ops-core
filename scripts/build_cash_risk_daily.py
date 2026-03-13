#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
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


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


def _days_until(as_of: str, target: Any) -> int | None:
    target_date = _to_date(target)
    if target_date is None:
        return None
    return (target_date - date.fromisoformat(as_of)).days


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        numerator_f = float(numerator)
        denominator_f = float(denominator)
    except (TypeError, ValueError):
        return None
    if denominator_f == 0:
        return None
    return round(numerator_f / denominator_f, 2)


def _driver_lines(payload: dict[str, Any]) -> list[str]:
    largest = payload.get("largest_po_commitment") or {}
    drivers = [
        (
            f"Base low-cash point is in {payload['days_to_base_min_cash']} days on "
            f"{payload['base_min_cash_date']}."
            if payload.get("days_to_base_min_cash") is not None
            else None
        ),
        (
            f"PO burden is {payload['po_burden_pct_of_base_min_cash']}% of the base minimum cash level."
            if payload.get("po_burden_pct_of_base_min_cash") is not None
            else None
        ),
        (
            f"Largest PO commitment is {largest.get('po_id')} ({largest.get('supplier_code')}) at "
            f"{largest.get('total_cost_cny')} CNY."
            if largest.get("po_id")
            else None
        ),
    ]
    return [line for line in drivers if line]


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Cash Risk Daily",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- base_min_cash_kzt: `{payload['base_min_cash_kzt']}` on `{payload['base_min_cash_date']}`",
        f"- conservative_min_cash_kzt: `{payload['conservative_min_cash_kzt']}` on `{payload['conservative_min_cash_date']}`",
        f"- opex_monthly_kzt: `{payload['opex_monthly_kzt']}`",
        f"- po_total_cogs_kzt: `{payload['po_total_cogs_kzt']}`",
        f"- real_pos_count: `{payload['real_pos_count']}`",
        "",
        "## Timing",
        "",
        f"- days_to_base_min_cash: `{payload.get('days_to_base_min_cash')}`",
        f"- days_to_conservative_min_cash: `{payload.get('days_to_conservative_min_cash')}`",
        f"- base_buffer_opex_months: `{payload.get('base_buffer_opex_months')}`",
        f"- conservative_buffer_opex_months: `{payload.get('conservative_buffer_opex_months')}`",
        "",
        "## Drivers",
        "",
    ]
    for line in payload.get("cash_risk_drivers") or []:
        lines.append(f"- {line}")
    largest = payload.get("largest_po_commitment") or {}
    lines.extend(
        [
            "",
            "## Largest PO Commitment",
            "",
            f"- po_id: `{largest.get('po_id')}`",
            f"- supplier_code: `{largest.get('supplier_code')}`",
            f"- units_total: `{largest.get('units_total')}`",
            f"- total_cost_cny: `{largest.get('total_cost_cny')}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_cash_risk_daily(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    cashfloor_gate_path: Path,
    po_dashboard_path: Path,
    output_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    cashfloor = _read_json(cashfloor_gate_path)
    po_dashboard = _read_json(po_dashboard_path)
    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and bool(cashfloor.get("ok"))
    )
    summary = po_dashboard.get("summary") or {}
    real_pos = po_dashboard.get("real_pos") or []
    top_po_commitments = sorted(
        [
            {
                "po_id": str(row.get("po_id") or ""),
                "supplier_code": str(row.get("supplier_code") or ""),
                "units_total": int(float(row.get("units_total") or 0)),
                "total_cost_cny": round(float(row.get("total_cost_cny") or 0.0), 2),
            }
            for row in real_pos
        ],
        key=lambda row: (row["total_cost_cny"], row["units_total"]),
        reverse=True,
    )[:5]
    largest_po_commitment = top_po_commitments[0] if top_po_commitments else None
    days_to_base = _days_until(as_of, cashfloor.get("base_min_cash_date"))
    days_to_conservative = _days_until(as_of, cashfloor.get("conservative_min_cash_date"))
    base_buffer_opex_months = _safe_ratio(cashfloor.get("base_min_cash_kzt"), cashfloor.get("opex_monthly_kzt"))
    conservative_buffer_opex_months = _safe_ratio(cashfloor.get("conservative_min_cash_kzt"), cashfloor.get("opex_monthly_kzt"))
    po_burden_pct_of_base_min_cash = _safe_ratio(summary.get("total_po_cogs_kzt"), cashfloor.get("base_min_cash_kzt"))
    po_burden_pct_of_conservative_min_cash = _safe_ratio(summary.get("total_po_cogs_kzt"), cashfloor.get("conservative_min_cash_kzt"))
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES",
        "base_min_cash_kzt": cashfloor.get("base_min_cash_kzt"),
        "base_min_cash_date": cashfloor.get("base_min_cash_date"),
        "conservative_min_cash_kzt": cashfloor.get("conservative_min_cash_kzt"),
        "conservative_min_cash_date": cashfloor.get("conservative_min_cash_date"),
        "opex_monthly_kzt": cashfloor.get("opex_monthly_kzt"),
        "po_total_cogs_kzt": summary.get("total_po_cogs_kzt"),
        "po_total_base_cost_kzt": summary.get("total_po_base_cost_kzt"),
        "po_total_dlv_kzt": summary.get("total_po_dlv_kzt"),
        "real_pos_count": len(real_pos),
        "days_to_base_min_cash": days_to_base,
        "days_to_conservative_min_cash": days_to_conservative,
        "base_buffer_opex_months": base_buffer_opex_months,
        "conservative_buffer_opex_months": conservative_buffer_opex_months,
        "po_burden_pct_of_base_min_cash": round((po_burden_pct_of_base_min_cash or 0.0) * 100, 2)
        if po_burden_pct_of_base_min_cash is not None else None,
        "po_burden_pct_of_conservative_min_cash": round((po_burden_pct_of_conservative_min_cash or 0.0) * 100, 2)
        if po_burden_pct_of_conservative_min_cash is not None else None,
        "largest_po_commitment": largest_po_commitment,
        "top_po_commitments": top_po_commitments,
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "cashfloor_gate": str(cashfloor_gate_path),
            "po_dashboard": str(po_dashboard_path),
        },
    }
    payload["cash_risk_drivers"] = _driver_lines(payload)
    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cash_risk_daily.json"
    md_path = out_dir / "cash_risk_daily.md"
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
    parser = argparse.ArgumentParser(description="Build cash risk daily surface.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--cashfloor-gate", type=Path, required=True)
    parser.add_argument("--po-dashboard", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/cash_risk_daily"))
    args = parser.parse_args()
    payload = build_cash_risk_daily(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        cashfloor_gate_path=args.cashfloor_gate,
        po_dashboard_path=args.po_dashboard,
        output_root=args.output_root,
        validation_root=args.validation_root,
    )
    print(f"cash_risk_daily_json={(args.output_root / args.as_of / 'cash_risk_daily.json').resolve()}")
    print(f"cash_risk_daily_md={(args.output_root / args.as_of / 'cash_risk_daily.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
