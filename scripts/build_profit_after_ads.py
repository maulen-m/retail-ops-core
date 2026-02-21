#!/usr/bin/env python3
"""Build profit-after-ads snapshot from published sales truth + ads sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.generate_business_insides import compute_sales_metrics

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _render_markdown(report: dict) -> str:
    rows = []
    for row in report["daily"]:
        rows.append(
            "| {date} | {net_rev} | {cogs} | {ads} | {profit} | {profit_after_ads} |".format(
                date=row["date"],
                net_rev=row["net_rev_kzt"],
                cogs=row["cogs_kzt"],
                ads=row["ads_spend_kzt"],
                profit=row["profit_kzt"],
                profit_after_ads=row["profit_after_ads_kzt"],
            )
        )

    lines = [
        "# Profit After Ads Snapshot",
        "",
        f"- As of: `{report['as_of_date']}`",
        f"- Ads status: `{report['ads_status']}` (reason: `{report['ads_reason']}`)",
        "",
        "| Date | Net Rev KZT | COGS KZT | Ads Spend KZT | Profit KZT | Profit After Ads KZT |",
        "|---|---:|---:|---:|---:|---:|",
        *rows,
    ]
    return "\n".join(lines) + "\n"


def build_profit_after_ads(*, db_path: Path, as_of: str | None = None, days: int = 7) -> dict:
    metrics = compute_sales_metrics(db_path=db_path, as_of=as_of, last_7_days=days)
    daily = []
    for row in metrics["last_7_days"]:
        daily.append(
            {
                "date": row["date"],
                "net_rev_kzt": row["net_rev_kzt"],
                "cogs_kzt": row["cogs_kzt"],
                "ads_spend_kzt": row["ads_spend_kzt"],
                "profit_kzt": row["profit_kzt"],
                "profit_after_ads_kzt": row["profit_after_ads_kzt"],
            }
        )
    return {
        "as_of_date": metrics["as_of_date"],
        "ads_status": metrics["ads"].get("status"),
        "ads_reason": metrics["ads"].get("reason"),
        "avg_7d_profit_kzt": metrics["avg_7d_profit_kzt"],
        "avg_7d_ads_spend_kzt": metrics["avg_7d_ads_spend_kzt"],
        "avg_7d_profit_after_ads_kzt": metrics["avg_7d_profit_after_ads_kzt"],
        "daily": daily,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build profit-after-ads snapshot")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()

    report = build_profit_after_ads(db_path=args.db, as_of=args.as_of, days=args.days)

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")

    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_render_markdown(report), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
