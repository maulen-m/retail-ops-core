#!/usr/bin/env python3
"""
Daily dry-run checker for on-delivery settlement residuals.

Default behavior is read-only:
- detect residual balances
- write markdown report under exports/
- return non-zero exit code when residuals exist

Optional Telegram alert is best-effort.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv as _load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.error_alerts import send_run_failure_alert
from scripts.reconcile_on_delivery_settlement import find_settlement_gaps

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "exports" / "on_delivery_residuals"


def load_repo_dotenv() -> None:
    _load_dotenv(PROJECT_ROOT / ".env", override=False)


def _render_report(
    *,
    residuals: list[dict[str, Any]],
    as_of: str,
    since: str | None,
    until: str | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# On-Delivery Residual Report ({as_of})")
    lines.append("")
    lines.append(f"- Window: `{since or 'MIN'}` -> `{until or as_of}`")
    lines.append(f"- Residual count: `{len(residuals)}`")
    lines.append("")
    if not residuals:
        lines.append("No residual balances detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Residuals")
    lines.append("")
    lines.append("| order_id | sku_id | status | balance_kzt | event_date |")
    lines.append("|---|---|---|---:|---|")
    for row in residuals:
        lines.append(
            "| {order_id} | {sku_id} | {status} | {balance_kzt:.2f} | {event_date} |".format(
                order_id=row.get("order_id", ""),
                sku_id=row.get("sku_id", ""),
                status=row.get("status", ""),
                balance_kzt=float(row.get("balance_kzt") or 0.0),
                event_date=row.get("event_date", ""),
            )
        )
    lines.append("")
    lines.append("## Apply Command")
    lines.append("")
    lines.append(
        "`ENABLE_CASHFLOW_WRITE=1 python3 scripts/reconcile_on_delivery_settlement.py "
        f"--since {since or as_of} --until {until or as_of} --apply`"
    )
    lines.append("")
    return "\n".join(lines)


def run_residual_check(
    *,
    db_path: Path = DEFAULT_DB,
    output_dir: Path = DEFAULT_EXPORT_DIR,
    since: str | None = None,
    until: str | None = None,
    tolerance_kzt: float = 1.0,
    send_alert: bool = False,
) -> dict[str, Any]:
    as_of = until or date.today().isoformat()
    residuals = find_settlement_gaps(
        db_path=db_path,
        since=since,
        until=until,
        tolerance_kzt=tolerance_kzt,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"on_delivery_residuals_{as_of}_{ts}.md"
    report_path.write_text(
        _render_report(
            residuals=residuals,
            as_of=as_of,
            since=since,
            until=until,
        ),
        encoding="utf-8",
    )

    exit_code = 3 if residuals else 0
    if send_alert and residuals:
        send_run_failure_alert(
            error_message=f"on_delivery residuals detected: {len(residuals)}",
            script_name="check_on_delivery_residuals",
            context=f"report={report_path}",
        )

    return {
        "exit_code": exit_code,
        "report_path": str(report_path),
        "residual_count": len(residuals),
    }


def main() -> int:
    load_repo_dotenv()
    parser = argparse.ArgumentParser(description="Dry-run residual check for on-delivery settlement gaps")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--tolerance-kzt", type=float, default=1.0)
    parser.add_argument("--send-alert", action="store_true")
    args = parser.parse_args()

    result = run_residual_check(
        db_path=args.db,
        output_dir=args.output_dir,
        since=args.since,
        until=args.until,
        tolerance_kzt=args.tolerance_kzt,
        send_alert=bool(args.send_alert),
    )
    print(f"report={result['report_path']}")
    print(f"residual_count={result['residual_count']}")
    if result["exit_code"] != 0:
        print("STATUS=FAIL")
    else:
        print("STATUS=PASS")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
