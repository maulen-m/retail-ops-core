#!/usr/bin/env python3
"""Build owner-facing monthly PnL surface with fail-closed decision-grade flags."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_ads_sidecar_readiness import validate_ads_sidecar_readiness
from scripts.validate_monthly_economics_parity import (
    validate_monthly_economics_parity,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAPPED_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "owner_pnl"
DEFAULT_PARITY_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "economics_parity"
DEFAULT_STATUSDATE_CUTOVER = date(2026, 2, 27)


class OwnerPnlError(RuntimeError):
    """Raised when strict owner PnL build fails."""


def _resolve_mapped_csv(*, mapped_root: Path, since: date, until: date, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
    else:
        path = (
            mapped_root.resolve()
            / f"{since.isoformat()}_to_{until.isoformat()}"
            / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
        )
    if not path.exists():
        raise OwnerPnlError(
            f"mapped archive csv missing: {path} (run export_sales_archive_statusdate_mapped.py first)"
        )
    return path


def _query_ads_monthly(*, db_path: Path, since: date, until: date) -> tuple[dict[tuple[str, str], float], bool]:
    if not db_path.exists():
        return {}, False
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ads_spend_sidecar_daily'"
        ).fetchone()
        if row is None:
            return {}, False
        rows = conn.execute(
            """
            SELECT
                substr(date(date), 1, 7) AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(COALESCE(total_cost_kzt, 0)) AS total_cost_kzt
            FROM ads_spend_sidecar_daily
            WHERE date(date) BETWEEN ? AND ?
            GROUP BY substr(date(date), 1, 7), UPPER(COALESCE(store_code, 'UNKNOWN'))
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    out: dict[tuple[str, str], float] = {}
    for r in rows:
        month = str(r["sale_month"] or "")
        store = str(r["store_code"] or "UNKNOWN")
        out[(month, store)] = round(float(r["total_cost_kzt"] or 0.0), 2)

    for month in sorted({k[0] for k in out}):
        month_sum = round(sum(v for (m, _), v in out.items() if m == month), 2)
        out[(month, "TOTAL")] = month_sum
    return out, True


def _fmt_kzt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f}"


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# OWNER PnL",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- since: `{report['since']}`",
        f"- status: `{report['status']}`",
        f"- ads_ready: `{str(bool(report['ads_readiness']['ok'])).lower()}`",
        f"- parity_status: `{report['economics_parity_status']}`",
        "",
        "## Monthly Totals",
        "",
        "| Month | Decision Grade | StatusDate Coverage | Net Rev KZT | COGS KZT | Ads KZT | Profit After Ads KZT |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["monthly_totals"]:
        lines.append(
            f"| `{row['sale_month']}` | `{str(bool(row['decision_grade'])).lower()}` | "
            f"{row['statusdate_coverage_pct']:.2f}% | {_fmt_kzt(row['net_rev_kzt'])} | "
            f"{_fmt_kzt(row['cogs_kzt'])} | {_fmt_kzt(row['ads_kzt'])} | {_fmt_kzt(row['profit_after_ads_kzt'])} |"
        )

    if report.get("monthly_by_store"):
        lines.extend(
            [
                "",
                "## Monthly By Store",
                "",
                "| Month | Store | Decision Grade | StatusDate Coverage | Net Rev KZT | COGS KZT | Ads KZT | Profit After Ads KZT |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in report["monthly_by_store"]:
            lines.append(
                f"| `{row['sale_month']}` | `{row['store_code']}` | "
                f"`{str(bool(row['decision_grade'])).lower()}` | {row['statusdate_coverage_pct']:.2f}% | "
                f"{_fmt_kzt(row['net_rev_kzt'])} | {_fmt_kzt(row['cogs_kzt'])} | {_fmt_kzt(row['ads_kzt'])} | "
                f"{_fmt_kzt(row['profit_after_ads_kzt'])} |"
            )

    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def build_owner_pnl_report(
    *,
    db_path: Path,
    as_of: date,
    since: date,
    mapped_root: Path,
    mapped_csv: Path | None,
    output_root: Path,
    parity_output_root: Path,
    include_store_breakdown: bool,
    strict: bool,
    tolerance_pct: float = 0.005,
    statusdate_cutover: date = DEFAULT_STATUSDATE_CUTOVER,
    ads_max_age_hours: float = 36.0,
    ads_min_mapping_coverage_pct: float = 85.0,
    ads_min_total_cost_kzt: float = 1.0,
) -> dict[str, Any]:
    if since > as_of:
        raise OwnerPnlError("since must be <= as_of")

    resolved_mapped_csv = _resolve_mapped_csv(
        mapped_root=mapped_root,
        since=since,
        until=as_of,
        explicit=mapped_csv,
    )

    parity = validate_monthly_economics_parity(
        since=since,
        until=as_of,
        db_path=db_path.resolve(),
        mapped_csv=resolved_mapped_csv,
        output_root=parity_output_root.resolve(),
        strict=False,
        tolerance_pct=float(tolerance_pct),
        statusdate_cutover=statusdate_cutover,
    )
    ads_readiness = validate_ads_sidecar_readiness(
        db_path=db_path.resolve(),
        as_of=as_of,
        output_root=PROJECT_ROOT / "exports" / "validation" / "ads_sidecar_readiness",
        max_age_hours=float(ads_max_age_hours),
        min_mapping_coverage_pct=float(ads_min_mapping_coverage_pct),
        min_total_cost_kzt=float(ads_min_total_cost_kzt),
        strict=False,
    )

    ads_monthly_map, ads_table_exists = _query_ads_monthly(
        db_path=db_path.resolve(),
        since=since,
        until=as_of,
    )

    by_store_rows: list[dict[str, Any]] = []
    for row in parity["rows"]:
        month = str(row["sale_month"])
        store = str(row["store_code"]).upper()
        decision_grade = bool(row.get("decision_grade"))
        coverage_pct = round(float(row.get("status_date_coverage") or 0.0) * 100.0, 2)
        ads_kzt = ads_monthly_map.get((month, store))
        publishable = bool(decision_grade and ads_readiness["ok"])

        net_rev = round(float(row.get("db_net_rev_kzt") or 0.0), 2) if publishable else None
        cogs = round(float(row.get("db_cogs_kzt") or 0.0), 2) if publishable else None
        profit = round(float(row.get("db_profit_kzt") or 0.0), 2) if publishable else None
        profit_after_ads = (
            round(profit - float(ads_kzt or 0.0), 2)
            if publishable and profit is not None and ads_kzt is not None
            else None
        )
        by_store_rows.append(
            {
                "sale_month": month,
                "store_code": store,
                "decision_grade": decision_grade,
                "statusdate_coverage_pct": coverage_pct,
                "net_rev_kzt": net_rev,
                "cogs_kzt": cogs,
                "ads_kzt": round(float(ads_kzt), 2) if ads_kzt is not None and publishable else None,
                "profit_after_ads_kzt": profit_after_ads,
                "locked_reason": None if publishable else "LOCKED_NOT_DECISION_GRADE_OR_ADS_NOT_READY",
            }
        )

    totals_rows: list[dict[str, Any]] = []
    df = pd.DataFrame(by_store_rows)
    for month in sorted(df["sale_month"].unique().tolist()) if not df.empty else []:
        month_rows = df[df["sale_month"] == month]
        decision_grade = bool((month_rows["decision_grade"] == True).all())  # noqa: E712
        publishable = bool(decision_grade and ads_readiness["ok"])
        parity_rows = [r for r in parity["rows"] if str(r["sale_month"]) == month]
        archive_rows = sum(int(float(r.get("archive_rows") or 0.0)) for r in parity_rows)
        if archive_rows > 0:
            coverage_pct = round(
                (
                    sum(
                        float(r.get("status_date_coverage") or 0.0)
                        * int(float(r.get("archive_rows") or 0.0))
                        for r in parity_rows
                    )
                    / float(archive_rows)
                )
                * 100.0,
                2,
            )
        else:
            coverage_pct = 0.0

        net_rev_val = round(sum(float(r.get("db_net_rev_kzt") or 0.0) for r in parity_rows), 2)
        cogs_val = round(sum(float(r.get("db_cogs_kzt") or 0.0) for r in parity_rows), 2)
        profit_val = round(sum(float(r.get("db_profit_kzt") or 0.0) for r in parity_rows), 2)
        ads_val = ads_monthly_map.get((month, "TOTAL"))

        totals_rows.append(
            {
                "sale_month": month,
                "decision_grade": decision_grade,
                "statusdate_coverage_pct": coverage_pct,
                "net_rev_kzt": net_rev_val if publishable else None,
                "cogs_kzt": cogs_val if publishable else None,
                "ads_kzt": round(float(ads_val), 2) if (publishable and ads_val is not None) else None,
                "profit_after_ads_kzt": (
                    round(profit_val - float(ads_val or 0.0), 2)
                    if publishable and ads_val is not None
                    else None
                ),
                "locked_reason": None if publishable else "LOCKED_NOT_DECISION_GRADE_OR_ADS_NOT_READY",
            }
        )

    errors: list[str] = []
    error_codes: list[str] = []
    if parity.get("status") != "PASS":
        error_codes.append("ECONOMICS_PARITY_FAIL")
        errors.append(
            f"economics parity status={parity.get('status')} decision_grade_mismatches={parity.get('decision_grade_mismatch_count')}"
        )
    if not ads_readiness.get("ok", False):
        error_codes.append("ADS_READINESS_FAIL")
        errors.append(
            f"ads readiness status={ads_readiness.get('status')} error_code={ads_readiness.get('error_code')}"
        )
    if not ads_table_exists:
        error_codes.append("ADS_TABLE_MISSING")
        errors.append("ads_spend_sidecar_daily table missing in operational DB")

    overall_ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    by_store_csv = out_dir / "owner_pnl_monthly_by_store.csv"
    totals_csv = out_dir / "owner_pnl_monthly_totals.csv"
    if by_store_rows:
        pd.DataFrame(by_store_rows).to_csv(by_store_csv, index=False, encoding="utf-8")
    else:
        by_store_csv.write_text("", encoding="utf-8")
    if totals_rows:
        pd.DataFrame(totals_rows).to_csv(totals_csv, index=False, encoding="utf-8")
    else:
        totals_csv.write_text("", encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "since": since.isoformat(),
        "status": "PASS" if overall_ok else "FAIL",
        "ok": overall_ok,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "db_path": str(db_path.resolve()),
        "mapped_csv": str(resolved_mapped_csv),
        "economics_parity_status": parity.get("status"),
        "economics_parity_summary_path": parity.get("summary_json"),
        "ads_readiness": {
            "ok": bool(ads_readiness.get("ok")),
            "status": ads_readiness.get("status"),
            "error_code": ads_readiness.get("error_code"),
            "mapping_coverage_pct": (
                (ads_readiness.get("ads_payload") or {}).get("mapping_coverage_pct")
            ),
            "total_cost_kzt": (ads_readiness.get("ads_payload") or {}).get("total_cost_kzt"),
            "json_path": ads_readiness.get("json_path"),
        },
        "monthly_totals": totals_rows,
        "monthly_by_store": by_store_rows if include_store_breakdown else [],
    }
    json_path = out_dir / "OWNER_PNL.json"
    md_path = out_dir / "OWNER_PNL.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    report["monthly_by_store_csv"] = str(by_store_csv)
    report["monthly_totals_csv"] = str(totals_csv)

    if strict and not overall_ok:
        raise OwnerPnlError("owner pnl build failed strict checks")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build fail-closed OWNER_PNL report.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--since",
        default=os.environ.get("AB_ECONOMICS_PARITY_SINCE", "2025-06-06"),
    )
    parser.add_argument("--mapped-root", type=Path, default=DEFAULT_MAPPED_ROOT)
    parser.add_argument("--mapped-csv", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--parity-output-root", type=Path, default=DEFAULT_PARITY_OUTPUT_ROOT)
    parser.add_argument("--include-store-breakdown", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--tolerance-pct", type=float, default=0.005)
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER.isoformat())
    parser.add_argument(
        "--ads-max-age-hours",
        type=float,
        default=float(os.environ.get("AB_ADS_DB_MAX_AGE_HOURS", "36")),
    )
    parser.add_argument(
        "--ads-min-mapping-coverage-pct",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_COVERAGE_PCT", "85")),
    )
    parser.add_argument(
        "--ads-min-total-cost-kzt",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_TOTAL_COST_KZT", "1")),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_owner_pnl_report(
        db_path=args.db,
        as_of=date.fromisoformat(str(args.as_of)),
        since=date.fromisoformat(str(args.since)),
        mapped_root=args.mapped_root,
        mapped_csv=args.mapped_csv,
        output_root=args.output_root,
        parity_output_root=args.parity_output_root,
        include_store_breakdown=bool(args.include_store_breakdown),
        strict=bool(args.strict),
        tolerance_pct=float(args.tolerance_pct),
        statusdate_cutover=date.fromisoformat(str(args.statusdate_cutover)),
        ads_max_age_hours=float(args.ads_max_age_hours),
        ads_min_mapping_coverage_pct=float(args.ads_min_mapping_coverage_pct),
        ads_min_total_cost_kzt=float(args.ads_min_total_cost_kzt),
    )
    print(f"owner_pnl_json={report['json_path']}")
    print(f"owner_pnl_md={report['md_path']}")
    print(f"owner_pnl_totals_csv={report['monthly_totals_csv']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
