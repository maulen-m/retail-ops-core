#!/usr/bin/env python3
"""Build deterministic conservative cashfloor gate artifact."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Cashfloor Gate",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- horizon_days: `{payload['horizon_days']}`",
        f"- opex_monthly_kzt: `{payload['opex_monthly_kzt']}`",
        f"- base_floor_kzt: `{payload['base_floor_kzt']}`",
        f"- base_min_cash_kzt: `{payload['base_min_cash_kzt']}`",
        f"- conservative_floor_kzt: `{payload['conservative_floor_kzt']}`",
        f"- conservative_min_cash_kzt: `{payload['conservative_min_cash_kzt']}`",
    ]
    if payload.get("reason"):
        lines.extend(["", "## Reason", "", f"- {payload['reason']}"])
    return "\n".join(lines) + "\n"


def validate_cashfloor(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    horizon_days: int = 60,
    strict: bool = False,
) -> dict[str, Any]:
    from scripts.cashflow_preflight_po import (
        ABSOLUTE_CASH_FLOOR_KZT,
        _load_monthly_opex,
        _load_scenarios_config,
        evaluate_preflight,
    )

    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        opex_monthly = _load_monthly_opex(conn, date.fromisoformat(as_of))

    cfg = _load_scenarios_config()
    abs_floor = float(cfg.get("cash_floor_abs_kzt", ABSOLUTE_CASH_FLOOR_KZT))
    base_mult = float(cfg.get("cash_floor_base_mult", 1.0))
    cons_mult = float(cfg.get("cash_floor_cons_mult", 1.5))
    refund_rate = float(cfg.get("refund_reserve_rate", 0.0))
    refund_days = int(cfg.get("refund_reserve_days", 14))

    base_floor = max(abs_floor, float(opex_monthly) * base_mult)
    cons_floor = float(opex_monthly) * cons_mult + abs_floor

    base_result = evaluate_preflight(
        db_path=db_path,
        horizon_days=horizon_days,
        scenario="base",
        min_cash_threshold=base_floor,
    )
    conservative_result = evaluate_preflight(
        db_path=db_path,
        horizon_days=horizon_days,
        scenario="conservative",
        min_cash_threshold=cons_floor,
        refund_rate=refund_rate,
        refund_days=refund_days,
        apply_reserve=True,
    )

    ok = base_result.ok and conservative_result.ok and opex_monthly > 0
    reason = None
    if opex_monthly <= 0:
        reason = "monthly OPEX commitments missing"
    elif not conservative_result.ok:
        reason = conservative_result.reason

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "GREEN" if ok else "RED",
        "ok": ok,
        "horizon_days": int(horizon_days),
        "opex_monthly_kzt": round(float(opex_monthly), 2),
        "base_floor_kzt": round(float(base_floor), 2),
        "base_min_cash_kzt": round(float(base_result.min_cash), 2),
        "base_min_cash_date": base_result.min_cash_date,
        "conservative_floor_kzt": round(float(cons_floor), 2),
        "conservative_min_cash_kzt": round(float(conservative_result.min_cash), 2),
        "conservative_min_cash_date": conservative_result.min_cash_date,
        "refund_reserve_rate": float(refund_rate),
        "refund_reserve_days": int(refund_days),
        "reason": reason,
    }

    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cashfloor_gate.json"
    md_path = out_dir / "cashfloor_gate.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": ok,
        "exit_code": 0 if (ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate conservative cashfloor gate")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--horizon-days", type=int, default=60)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_cashfloor(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        horizon_days=args.horizon_days,
        strict=bool(args.strict),
    )
    print(f"cashfloor_gate_json={report['json_path']}")
    print(f"cashfloor_gate_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
