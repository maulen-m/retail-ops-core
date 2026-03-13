#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rebuild_cashflow_calendar import rebuild_cashflow_calendar


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _to_float(value: Any) -> float:
    return round(float(value or 0.0), 2)


def _driver_for_row(row: dict[str, Any]) -> str:
    candidates = [
        ("PO_PAYMENTS", _to_float(row.get("po_payments_kzt"))),
        ("EXPENSES", _to_float(row.get("expenses_kzt"))),
        ("REFUNDS", _to_float(row.get("refunds_kzt"))),
        ("COGS", _to_float(row.get("cogs_kzt"))),
        ("PAYOUTS", abs(_to_float(row.get("payouts_received_kzt")))),
    ]
    candidates.sort(key=lambda item: item[1], reverse=True)
    if not candidates or candidates[0][1] <= 0:
        return "UNKNOWN"
    return candidates[0][0]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": str(row.get("date") or ""),
        "cash_close": _to_float(row.get("cash_close")),
        "cash_flow_kzt": _to_float(row.get("cash_flow_kzt")),
        "po_payments_kzt": _to_float(row.get("po_payments_kzt")),
        "expenses_kzt": _to_float(row.get("expenses_kzt")),
        "refunds_kzt": _to_float(row.get("refunds_kzt")),
        "payouts_received_kzt": _to_float(row.get("payouts_received_kzt")),
        "cogs_kzt": _to_float(row.get("cogs_kzt")),
        "primary_driver": _driver_for_row(row),
    }


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Cashflow Calendar Daily",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- start_date: `{payload['calendar_window']['start_date']}`",
        f"- end_date: `{payload['calendar_window']['end_date']}`",
        f"- days: `{payload['calendar_window']['days']}`",
        f"- base_min_cash_kzt: `{payload['base_min_cash_kzt']}` on `{payload['base_min_cash_date']}`",
        f"- conservative_min_cash_kzt: `{payload['conservative_min_cash_kzt']}` on `{payload['conservative_min_cash_date']}`",
        "",
        "## Critical Days",
        "",
    ]
    critical_days = payload.get("critical_days") or []
    if not critical_days:
        lines.append("- none")
    else:
        for row in critical_days:
            lines.append(
                f"- `{row['date']}`: cash_close=`{row['cash_close']}`, cash_flow_kzt=`{row['cash_flow_kzt']}`, primary_driver=`{row['primary_driver']}`"
            )

    lines.extend(["", "## Largest Outflow Days", ""])
    outflow_days = payload.get("largest_outflow_days") or []
    if not outflow_days:
        lines.append("- none")
    else:
        for row in outflow_days:
            lines.append(
                f"- `{row['date']}`: cash_flow_kzt=`{row['cash_flow_kzt']}`, primary_driver=`{row['primary_driver']}`"
            )

    lines.extend(
        [
            "",
            "## Floor Breach Dates",
            "",
            f"- base_floor_breach_dates: `{payload.get('base_floor_breach_dates') or []}`",
            f"- conservative_floor_breach_dates: `{payload.get('conservative_floor_breach_dates') or []}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _coerce_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_row(row) for row in rows if row.get("date")]
    return sorted(normalized, key=lambda row: row["date"])


def build_cashflow_calendar_daily(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    cashflow_scorecard_path: Path,
    cashfloor_gate_path: Path,
    db_path: Path,
    output_root: Path,
    validation_root: Path,
    horizon_days: int = 30,
    daily_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    cashflow_scorecard = _read_json(cashflow_scorecard_path)
    cashfloor = _read_json(cashfloor_gate_path)
    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and str(cashflow_scorecard.get("status")) == "GREEN"
        and bool(cashfloor.get("ok", cashfloor.get("status") == "GREEN"))
    )

    if daily_rows is None:
        start_date = date.fromisoformat(as_of)
        end_date = start_date + timedelta(days=max(horizon_days - 1, 0))
        dry_daily_rows, _ = rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=start_date,
            end_date=end_date,
            apply=False,
            run_id=f"owner_calendar_{as_of.replace('-', '')}",
        )
        daily_rows = dry_daily_rows

    rows = _coerce_rows(daily_rows)
    if rows:
        start_date = rows[0]["date"]
        end_date = rows[-1]["date"]
    else:
        start_date = as_of
        end_date = as_of

    base_floor = _to_float(cashfloor.get("base_floor_kzt"))
    conservative_floor = _to_float(cashfloor.get("conservative_floor_kzt"))
    base_floor_breach_dates = [row["date"] for row in rows if row["cash_close"] <= base_floor]
    conservative_floor_breach_dates = [row["date"] for row in rows if row["cash_close"] <= conservative_floor]
    critical_days = sorted(rows, key=lambda row: (row["cash_close"], row["date"]))[:5]
    largest_outflow_days = sorted(rows, key=lambda row: (row["cash_flow_kzt"], row["date"]))[:5]

    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES",
        "calendar_window": {
            "start_date": start_date,
            "end_date": end_date,
            "days": len(rows),
        },
        "base_min_cash_kzt": _to_float(cashfloor.get("base_min_cash_kzt")),
        "base_min_cash_date": cashfloor.get("base_min_cash_date"),
        "conservative_min_cash_kzt": _to_float(cashfloor.get("conservative_min_cash_kzt")),
        "conservative_min_cash_date": cashfloor.get("conservative_min_cash_date"),
        "critical_days": critical_days,
        "largest_outflow_days": largest_outflow_days,
        "base_floor_breach_dates": base_floor_breach_dates,
        "conservative_floor_breach_dates": conservative_floor_breach_dates,
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "cashflow_scorecard": str(cashflow_scorecard_path),
            "cashfloor_gate": str(cashfloor_gate_path),
            "db_path": str(db_path),
        },
    }

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cashflow_calendar_daily.json"
    md_path = out_dir / "cashflow_calendar_daily.md"
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
    parser = argparse.ArgumentParser(description="Build owner-facing cashflow calendar daily surface.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--cashflow-scorecard", type=Path, required=True)
    parser.add_argument("--cashfloor-gate", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/cashflow_calendar_daily"))
    parser.add_argument("--horizon-days", type=int, default=30)
    args = parser.parse_args()

    payload = build_cashflow_calendar_daily(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        cashflow_scorecard_path=args.cashflow_scorecard,
        cashfloor_gate_path=args.cashfloor_gate,
        db_path=args.db,
        output_root=args.output_root,
        validation_root=args.validation_root,
        horizon_days=args.horizon_days,
    )
    print(f"cashflow_calendar_daily_json={(args.output_root / args.as_of / 'cashflow_calendar_daily.json').resolve()}")
    print(f"cashflow_calendar_daily_md={(args.output_root / args.as_of / 'cashflow_calendar_daily.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
