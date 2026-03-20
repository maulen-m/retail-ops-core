#!/usr/bin/env python3
"""Validate semantic consistency across owner-facing daily surfaces."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_stale_language(brief: dict[str, Any]) -> bool:
    haystacks = [str(brief.get("headline") or "")]
    haystacks.extend(str(item) for item in (brief.get("owner_actions") or []))
    text = " ".join(haystacks).lower()
    return "stale" in text


def _check(report: list[dict[str, Any]], *, ok: bool, code: str, message: str) -> None:
    report.append({"code": code, "ok": ok, "message": message})


def build_owner_surface_consistency_report(
    *,
    as_of: str,
    owner_profit_path: Path,
    cash_risk_path: Path,
    cashflow_calendar_path: Path,
    po_sku_path: Path,
    owner_daily_brief_path: Path,
) -> dict[str, Any]:
    owner_profit = _load_json(owner_profit_path)
    cash_risk = _load_json(cash_risk_path)
    cashflow_calendar = _load_json(cashflow_calendar_path)
    po_sku = _load_json(po_sku_path)
    brief = _load_json(owner_daily_brief_path)

    checks: list[dict[str, Any]] = []
    brief_sections = brief.get("sections") or {}
    _check(
        checks,
        ok=(brief_sections.get("profit") or {}).get("trust_banner") == owner_profit.get("trust_banner"),
        code="BRIEF_PROFIT_TRUST_BANNER_MATCH",
        message="brief profit trust banner must match owner_profit_daily",
    )
    _check(
        checks,
        ok=(brief_sections.get("cash_risk") or {}).get("trust_banner") == cash_risk.get("trust_banner"),
        code="BRIEF_CASH_RISK_TRUST_BANNER_MATCH",
        message="brief cash_risk trust banner must match cash_risk_daily",
    )
    _check(
        checks,
        ok=(brief_sections.get("cashflow_calendar") or {}).get("trust_banner") == cashflow_calendar.get("trust_banner"),
        code="BRIEF_CASHFLOW_TRUST_BANNER_MATCH",
        message="brief cashflow trust banner must match cashflow_calendar_daily",
    )
    _check(
        checks,
        ok=(brief_sections.get("po_sku") or {}).get("trust_banner") == po_sku.get("trust_banner"),
        code="BRIEF_PO_TRUST_BANNER_MATCH",
        message="brief po_sku trust banner must match po_sku_daily",
    )
    _check(
        checks,
        ok=(brief_sections.get("profit") or {}).get("decision_scope") == owner_profit.get("decision_scope"),
        code="BRIEF_PROFIT_DECISION_SCOPE_MATCH",
        message="brief decision scope must match owner_profit_daily",
    )

    planning_freshness = ((po_sku.get("planning_snapshot") or {}).get("freshness") or "").strip()
    if planning_freshness == "STALE_VS_CUTOFF":
        _check(
            checks,
            ok=_contains_stale_language(brief),
            code="STALE_PO_VISIBLE_IN_BRIEF",
            message="stale PO planning must remain visible in the owner brief headline/actions",
        )

    largest_outflow_days = cashflow_calendar.get("largest_outflow_days") or []
    nonnegative_outflow_rows = [row for row in largest_outflow_days if float(row.get("cash_flow_kzt") or 0.0) >= 0]
    unknown_driver_rows = [row for row in largest_outflow_days if str(row.get("primary_driver") or "") == "UNKNOWN"]
    _check(
        checks,
        ok=not nonnegative_outflow_rows,
        code="LARGEST_OUTFLOW_NEGATIVE_ONLY",
        message="largest_outflow_days must include only rows with negative cash_flow_kzt",
    )
    _check(
        checks,
        ok=not unknown_driver_rows,
        code="LARGEST_OUTFLOW_DRIVER_RESOLVED",
        message="largest_outflow_days must not expose UNKNOWN primary_driver",
    )

    critical_days = cashflow_calendar.get("critical_days") or []
    if critical_days:
        first_driver = str(critical_days[0].get("primary_driver") or "").strip()
        if first_driver == "UNKNOWN":
            _check(
                checks,
                ok="unresolved modeled driver" in str(brief.get("headline") or "").lower()
                or any("unresolved driver" in str(item).lower() for item in (brief.get("owner_actions") or [])),
                code="UNKNOWN_CRITICAL_DRIVER_EXPLAINED_IN_BRIEF",
                message="if critical day driver is UNKNOWN, brief must explicitly say the driver is unresolved",
            )

    ok = all(item["ok"] for item in checks)
    return {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "checks": checks,
        "sources": {
            "owner_profit_daily": str(owner_profit_path),
            "cash_risk_daily": str(cash_risk_path),
            "cashflow_calendar_daily": str(cashflow_calendar_path),
            "po_sku_daily": str(po_sku_path),
            "owner_daily_brief": str(owner_daily_brief_path),
        },
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Owner Surface Consistency Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        "",
        "## Checks",
        "",
    ]
    for item in report.get("checks") or []:
        lines.append(f"- `{item['code']}`: `{'PASS' if item['ok'] else 'FAIL'}` — {item['message']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate owner-surface semantic consistency.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-profit", type=Path, required=True)
    parser.add_argument("--cash-risk", type=Path, required=True)
    parser.add_argument("--cashflow-calendar", type=Path, required=True)
    parser.add_argument("--po-sku", type=Path, required=True)
    parser.add_argument("--owner-daily-brief", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    report = build_owner_surface_consistency_report(
        as_of=args.as_of,
        owner_profit_path=args.owner_profit,
        cash_risk_path=args.cash_risk,
        cashflow_calendar_path=args.cashflow_calendar,
        po_sku_path=args.po_sku,
        owner_daily_brief_path=args.owner_daily_brief,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output_md.write_text(_render_md(report), encoding="utf-8")
    print(f"output_json={args.output_json.resolve()}")
    print(f"output_md={args.output_md.resolve()}")
    print(f"status={report['status']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
