#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_cash_risk_daily import build_cash_risk_daily
from scripts.build_cashflow_calendar_daily import build_cashflow_calendar_daily
from scripts.build_domain_scorecards import build_domain_scorecards
from scripts.build_owner_daily_brief import build_owner_daily_brief
from scripts.build_owner_profit_daily import build_owner_profit_daily
from scripts.build_po_sku_daily import build_po_sku_daily


ScorecardBuilder = Callable[..., dict[str, Any]]
CashflowCalendarBuilder = Callable[..., dict[str, Any]]


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_owner_review_cycle(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    review_dir: Path,
    cashfloor_gate_path: Path,
    db_path: Path,
    po_dashboard_path: Path,
    owner_output_root: Path,
    owner_profit_validation_root: Path,
    cash_risk_validation_root: Path,
    cashflow_calendar_validation_root: Path,
    po_sku_validation_root: Path,
    owner_daily_brief_validation_root: Path,
    scorecard_output_root: Path,
    scorecard_report_path: Path,
    scorecard_builder: ScorecardBuilder = build_domain_scorecards,
    cashflow_calendar_builder: CashflowCalendarBuilder = build_cashflow_calendar_daily,
    project_root: Path = Path("."),
) -> dict[str, Any]:
    owner_profit = build_owner_profit_daily(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary_path,
        system_health_path=system_health_path,
        review_dir=review_dir,
        output_root=owner_output_root,
        validation_root=owner_profit_validation_root,
    )
    cash_risk = build_cash_risk_daily(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary_path,
        system_health_path=system_health_path,
        cashfloor_gate_path=cashfloor_gate_path,
        po_dashboard_path=po_dashboard_path,
        output_root=owner_output_root,
        validation_root=cash_risk_validation_root,
    )
    scorecards = scorecard_builder(
        project_root=Path(project_root),
        as_of=as_of,
        output_root=scorecard_output_root,
        strict=True,
    )
    cashflow_calendar = cashflow_calendar_builder(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary_path,
        system_health_path=system_health_path,
        cashflow_scorecard_path=scorecard_output_root / as_of / "cashflow_scorecard.json",
        cashfloor_gate_path=cashfloor_gate_path,
        db_path=db_path,
        output_root=owner_output_root,
        validation_root=cashflow_calendar_validation_root,
    )
    po_sku = build_po_sku_daily(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary_path,
        system_health_path=system_health_path,
        po_dashboard_path=po_dashboard_path,
        output_root=owner_output_root,
        validation_root=po_sku_validation_root,
    )
    brief = build_owner_daily_brief(
        as_of=as_of,
        owner_profit_path=owner_output_root / as_of / "owner_profit_daily.json",
        cash_risk_path=owner_output_root / as_of / "cash_risk_daily.json",
        cashflow_calendar_path=owner_output_root / as_of / "cashflow_calendar_daily.json",
        po_sku_path=owner_output_root / as_of / "po_sku_daily.json",
        output_root=owner_output_root,
        validation_root=owner_daily_brief_validation_root,
    )

    lines = [
        "# Scorecard Refresh Report",
        "",
        f"- generated_at: `{_now_utc()}`",
        f"- as_of: `{as_of}`",
        f"- owner_profit_status: `{owner_profit['status']}`",
        f"- cash_risk_status: `{cash_risk['status']}`",
        f"- cashflow_calendar_daily_status: `{cashflow_calendar['status']}`",
        f"- po_sku_status: `{po_sku['status']}`",
        f"- owner_daily_brief_status: `{brief['status']}`",
        f"- scorecard_status: `{'PASS' if scorecards.get('ok') else 'FAIL'}`",
        "",
        "## Scorecard Artifacts",
        "",
    ]
    scorecard_dir = Path(scorecards.get("output_dir", ""))
    if scorecard_dir:
        for json_file in sorted(scorecard_dir.glob("*_scorecard.json")):
            lines.append(f"- `{json_file.name}`")
    _write_md(scorecard_report_path, lines)

    return {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS"
        if owner_profit["ok"] and cash_risk["ok"] and cashflow_calendar["ok"] and po_sku["ok"] and brief["ok"] and bool(scorecards.get("ok"))
        else "FAIL",
        "owner_profit": {"status": owner_profit["status"], "path": str((owner_output_root / as_of / "owner_profit_daily.json").resolve())},
        "cash_risk": {"status": cash_risk["status"], "path": str((owner_output_root / as_of / "cash_risk_daily.json").resolve())},
        "cashflow_calendar_daily": {
            "status": cashflow_calendar["status"],
            "path": str((owner_output_root / as_of / "cashflow_calendar_daily.json").resolve()),
        },
        "po_sku": {"status": po_sku["status"], "path": str((owner_output_root / as_of / "po_sku_daily.json").resolve())},
        "owner_daily_brief": {"status": brief["status"], "path": str((owner_output_root / as_of / "owner_daily_brief.json").resolve())},
        "scorecards": {"status": "PASS" if scorecards.get("ok") else "FAIL", "output_dir": str(scorecard_dir.resolve()) if scorecard_dir else None},
        "scorecard_report_path": str(scorecard_report_path.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh owner daily surfaces, brief, and scorecards.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--owner-truth-summary", type=Path, default=None)
    parser.add_argument("--system-health", type=Path, default=None)
    parser.add_argument("--review-dir", type=Path, default=None)
    parser.add_argument("--cashfloor-gate", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=Path("db/app.db"))
    parser.add_argument("--po-dashboard", type=Path, default=Path("exports/po_dashboard_data.json"))
    parser.add_argument("--owner-output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--owner-profit-validation-root", type=Path, default=Path("exports/validation/owner_profit_daily"))
    parser.add_argument("--cash-risk-validation-root", type=Path, default=Path("exports/validation/cash_risk_daily"))
    parser.add_argument("--cashflow-calendar-validation-root", type=Path, default=Path("exports/validation/cashflow_calendar_daily"))
    parser.add_argument("--po-sku-validation-root", type=Path, default=Path("exports/validation/po_sku_daily"))
    parser.add_argument("--owner-daily-brief-validation-root", type=Path, default=Path("exports/validation/owner_daily_brief"))
    parser.add_argument("--scorecard-output-root", type=Path, default=Path("exports/daily"))
    parser.add_argument("--scorecard-report-path", type=Path, required=True)
    args = parser.parse_args()

    owner_truth_summary_path = args.owner_truth_summary or (Path("exports/daily") / args.as_of / "owner_truth_summary.json")
    system_health_path = args.system_health or (Path("exports/diagnostics") / args.as_of / "system_health.json")
    review_dir = args.review_dir or (Path("exports/north_star_owner_review") / args.as_of)
    cashfloor_gate_path = args.cashfloor_gate or (Path("exports/daily") / args.as_of / "cashfloor_gate.json")

    report = run_owner_review_cycle(
        as_of=args.as_of,
        owner_truth_summary_path=owner_truth_summary_path,
        system_health_path=system_health_path,
        review_dir=review_dir,
        cashfloor_gate_path=cashfloor_gate_path,
        db_path=args.db,
        po_dashboard_path=args.po_dashboard,
        owner_output_root=args.owner_output_root,
        owner_profit_validation_root=args.owner_profit_validation_root,
        cash_risk_validation_root=args.cash_risk_validation_root,
        cashflow_calendar_validation_root=args.cashflow_calendar_validation_root,
        po_sku_validation_root=args.po_sku_validation_root,
        owner_daily_brief_validation_root=args.owner_daily_brief_validation_root,
        scorecard_output_root=args.scorecard_output_root,
        scorecard_report_path=args.scorecard_report_path,
        project_root=args.project_root,
    )
    print(f"owner_review_cycle_status={report['status']}")
    print(f"scorecard_report_path={report['scorecard_report_path']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
