#!/usr/bin/env python3
"""Fail-closed monthly economics parity: DB truth vs status-date mapped archive."""

from __future__ import annotations

import argparse
from calendar import monthrange
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAPPED_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "economics_parity"
DEFAULT_STATUSDATE_CUTOVER = "2026-02-27"


class ParityError(RuntimeError):
    """Raised when strict parity checks fail."""


def _month_end(month_key: str) -> date:
    year, month = month_key.split("-")
    y = int(year)
    m = int(month)
    return date(y, m, monthrange(y, m)[1])


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _resolve_mapped_csv(*, since: date, until: date, explicit: Path | None, mapped_root: Path) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
    else:
        path = (
            mapped_root.resolve()
            / f"{since.isoformat()}_to_{until.isoformat()}"
            / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
        )
    if not path.exists():
        raise ParityError(
            f"mapped archive csv missing: {path}. Run scripts/export_sales_archive_statusdate_mapped.py first."
        )
    return path


def _load_archive_monthly(*, mapped_csv: Path, since: date, until: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(mapped_csv, dtype=str, keep_default_na=False)
    if df.empty:
        raise ParityError("mapped archive csv contains 0 rows")

    required_cols = {
        "transaction_date",
        "store_code",
        "order_id",
        "quantity",
        "net_rev_kzt",
        "status_internal",
        "return_flag",
        "transaction_date_source",
    }
    missing = sorted(required_cols - set(df.columns))
    if missing:
        raise ParityError(f"mapped archive csv missing columns: {', '.join(missing)}")

    tx = pd.to_datetime(df["transaction_date"], errors="coerce")
    mask_range = (tx.dt.date >= since) & (tx.dt.date <= until)
    df = df[mask_range].copy()
    if df.empty:
        raise ParityError("mapped archive has 0 rows in requested range")

    delivered = (
        df["status_internal"].astype(str).str.upper().eq("DELIVERED")
        & pd.to_numeric(df["return_flag"], errors="coerce").fillna(0).astype(int).eq(0)
    )
    df = df[delivered].copy()
    if df.empty:
        raise ParityError("mapped archive has 0 delivered rows in requested range")

    df["sale_month"] = pd.to_datetime(df["transaction_date"], errors="coerce").dt.to_period("M").astype(str)
    df["store_code"] = df["store_code"].astype(str).str.upper()
    df["units"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0.0)
    df["net_rev_kzt"] = pd.to_numeric(df["net_rev_kzt"], errors="coerce").fillna(0.0)

    monthly_archive = (
        df.groupby(["sale_month", "store_code"], dropna=False)
        .agg(
            archive_units=("units", "sum"),
            archive_net_rev_kzt=("net_rev_kzt", "sum"),
            archive_orders=("order_id", "nunique"),
            archive_rows=("order_id", "count"),
            status_date_rows=(
                "transaction_date_source",
                lambda s: int(s.isin(["status_change_date", "ui_override_status_date"]).sum()),
            ),
            fallback_rows=(
                "transaction_date_source",
                lambda s: int((s == "creation_date_fallback").sum()),
            ),
        )
        .reset_index()
        .sort_values(["sale_month", "store_code"])
        .reset_index(drop=True)
    )
    monthly_archive["status_date_coverage"] = monthly_archive.apply(
        lambda r: (float(r["status_date_rows"]) / float(r["archive_rows"])) if float(r["archive_rows"]) > 0 else 0.0,
        axis=1,
    )

    return monthly_archive, df


def _load_db_monthly(*, db_path: Path, since: date, until: date) -> pd.DataFrame:
    if not db_path.exists():
        raise ParityError(f"db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_sales_truth_views(conn)
        rows = conn.execute(
            """
            SELECT
                substr(date(sale_date), 1, 7) AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(COALESCE(units, 0)) AS db_units,
                SUM(COALESCE(net_rev_kzt, 0)) AS db_net_rev_kzt,
                SUM(COALESCE(cogs_kzt, 0)) AS db_cogs_kzt,
                SUM(COALESCE(profit_kzt, 0)) AS db_profit_kzt,
                COUNT(DISTINCT CAST(order_id AS TEXT)) AS db_orders
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY substr(date(sale_date), 1, 7), UPPER(COALESCE(store_code, 'UNKNOWN'))
            ORDER BY 1, 2
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(
            columns=[
                "sale_month",
                "store_code",
                "db_units",
                "db_net_rev_kzt",
                "db_cogs_kzt",
                "db_profit_kzt",
                "db_orders",
            ]
        )

    df = pd.DataFrame([dict(r) for r in rows])
    numeric_cols = ["db_units", "db_net_rev_kzt", "db_cogs_kzt", "db_profit_kzt", "db_orders"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Monthly Economics Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- range: `{report['since']} -> {report['until']}`",
        f"- status: `{report['status']}`",
        f"- strict: `{str(report['strict']).lower()}`",
        f"- tolerance_pct: `{report['tolerance_pct']}`",
        f"- decision_grade_mismatches: `{report['decision_grade_mismatch_count']}`",
        f"- provisional_month_store_pairs: `{report['provisional_pair_count']}`",
        "",
        "| sale_month | store_code | archive_units | db_units | archive_net_rev | db_net_rev | decision_grade | db_exceeds_archive |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['sale_month']}` | `{row['store_code']}` | {row['archive_units']:.2f} | {row['db_units']:.2f} | "
            f"{row['archive_net_rev_kzt']:.2f} | {row['db_net_rev_kzt']:.2f} | "
            f"{str(row['decision_grade']).lower()} | {str(row['db_exceeds_archive']).lower()} |"
        )

    if report["decision_grade_mismatches"]:
        lines.extend(["", "## Decision-Grade Mismatches", ""])
        for msg in report["decision_grade_mismatches"]:
            lines.append(f"- {msg}")

    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def validate_monthly_economics_parity(
    *,
    since: date,
    until: date,
    db_path: Path,
    mapped_csv: Path,
    output_root: Path,
    strict: bool,
    tolerance_pct: float,
    statusdate_cutover: date,
) -> dict[str, Any]:
    if until < since:
        raise ParityError("until must be >= since")
    if tolerance_pct < 0:
        raise ParityError("tolerance_pct must be >= 0")

    monthly_archive, delivered_rows = _load_archive_monthly(
        mapped_csv=mapped_csv,
        since=since,
        until=until,
    )
    monthly_db = _load_db_monthly(db_path=db_path, since=since, until=until)

    merged = monthly_archive.merge(monthly_db, on=["sale_month", "store_code"], how="outer").fillna(0)
    merged = merged.sort_values(["sale_month", "store_code"]).reset_index(drop=True)

    decision_grade_mismatches: list[str] = []
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    provisional_pairs = 0
    for _, row in merged.iterrows():
        sale_month = str(row["sale_month"])
        store_code = str(row["store_code"]).upper()
        archive_units = _safe_float(row.get("archive_units"))
        archive_net_rev = _safe_float(row.get("archive_net_rev_kzt"))
        db_units = _safe_float(row.get("db_units"))
        db_net_rev = _safe_float(row.get("db_net_rev_kzt"))

        fallback_rows = int(round(_safe_float(row.get("fallback_rows"))))
        archive_rows = int(round(_safe_float(row.get("archive_rows"))))
        status_date_coverage = _safe_float(row.get("status_date_coverage"))

        month_end = _month_end(sale_month)
        closed_month = month_end < until
        month_is_pre_cutover = month_end < statusdate_cutover

        decision_grade = bool(closed_month and not month_is_pre_cutover and fallback_rows == 0)
        if not decision_grade:
            provisional_pairs += 1

        units_threshold = archive_units * (1.0 + tolerance_pct)
        rev_threshold = archive_net_rev * (1.0 + tolerance_pct)
        units_exceeds = db_units > units_threshold + 1e-9
        rev_exceeds = db_net_rev > rev_threshold + 1.0
        db_exceeds = bool(units_exceeds or rev_exceeds)

        if decision_grade and db_exceeds:
            decision_grade_mismatches.append(
                f"{sale_month} {store_code}: db_units={db_units:.2f} archive_units={archive_units:.2f} "
                f"db_net_rev={db_net_rev:.2f} archive_net_rev={archive_net_rev:.2f}"
            )

        rows.append(
            {
                "sale_month": sale_month,
                "store_code": store_code,
                "archive_units": archive_units,
                "archive_net_rev_kzt": archive_net_rev,
                "archive_orders": int(round(_safe_float(row.get("archive_orders")))),
                "archive_rows": archive_rows,
                "status_date_rows": int(round(_safe_float(row.get("status_date_rows")))),
                "fallback_rows": fallback_rows,
                "status_date_coverage": status_date_coverage,
                "db_units": db_units,
                "db_net_rev_kzt": db_net_rev,
                "db_cogs_kzt": _safe_float(row.get("db_cogs_kzt")),
                "db_profit_kzt": _safe_float(row.get("db_profit_kzt")),
                "db_orders": int(round(_safe_float(row.get("db_orders")))),
                "closed_month": closed_month,
                "month_pre_cutover": month_is_pre_cutover,
                "decision_grade": decision_grade,
                "db_exceeds_archive": db_exceeds,
                "units_diff": db_units - archive_units,
                "net_rev_diff_kzt": db_net_rev - archive_net_rev,
            }
        )

    if provisional_pairs > 0:
        notes.append(
            f"{provisional_pairs} month/store pairs are provisional (pre-cutover or creation-date fallback present)."
        )
    notes.append(
        f"statusdate_cutover={statusdate_cutover.isoformat()} (months ending before this are provisional by contract)."
    )

    range_dir = output_root.resolve() / f"{since.isoformat()}_to_{until.isoformat()}"
    range_dir.mkdir(parents=True, exist_ok=True)

    monthly_archive_csv = range_dir / "monthly_archive.csv"
    monthly_db_csv = range_dir / "monthly_db.csv"
    diffs_csv = range_dir / "diffs_by_month.csv"
    summary_json = range_dir / "summary.json"
    report_md = range_dir / "report.md"

    monthly_archive.to_csv(monthly_archive_csv, index=False, encoding="utf-8")
    monthly_db.to_csv(monthly_db_csv, index=False, encoding="utf-8")
    pd.DataFrame(rows).to_csv(diffs_csv, index=False, encoding="utf-8")

    status = "PASS" if not decision_grade_mismatches else "FAIL"
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "strict": bool(strict),
        "status": status,
        "tolerance_pct": float(tolerance_pct),
        "statusdate_cutover": statusdate_cutover.isoformat(),
        "decision_grade_mismatch_count": len(decision_grade_mismatches),
        "decision_grade_mismatches": decision_grade_mismatches,
        "provisional_pair_count": provisional_pairs,
        "notes": notes,
        "mapped_csv": str(mapped_csv.resolve()),
        "monthly_archive_csv": str(monthly_archive_csv.resolve()),
        "monthly_db_csv": str(monthly_db_csv.resolve()),
        "diffs_by_month_csv": str(diffs_csv.resolve()),
        "summary_json": str(summary_json.resolve()),
        "report_md": str(report_md.resolve()),
        "rows": rows,
        "archive_delivered_rows": int(len(delivered_rows)),
    }

    summary_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")

    if strict and status != "PASS":
        raise ParityError("monthly economics parity failed on decision-grade month(s)")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate monthly economics parity (DB vs mapped archive)")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mapped-csv", type=Path, default=None)
    parser.add_argument("--mapped-root", type=Path, default=DEFAULT_MAPPED_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--tolerance-pct", type=float, default=0.005)
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    since = date.fromisoformat(args.since)
    until = date.fromisoformat(args.until)
    mapped_csv = _resolve_mapped_csv(
        since=since,
        until=until,
        explicit=args.mapped_csv,
        mapped_root=args.mapped_root,
    )

    report = validate_monthly_economics_parity(
        since=since,
        until=until,
        db_path=args.db,
        mapped_csv=mapped_csv,
        output_root=args.output_root,
        strict=bool(args.strict),
        tolerance_pct=float(args.tolerance_pct),
        statusdate_cutover=date.fromisoformat(args.statusdate_cutover),
    )

    print(f"monthly_economics_parity_summary_json={report['summary_json']}")
    print(f"monthly_economics_parity_report_md={report['report_md']}")
    print(f"monthly_db_csv={report['monthly_db_csv']}")
    print(f"monthly_archive_csv={report['monthly_archive_csv']}")
    print(f"diffs_by_month_csv={report['diffs_by_month_csv']}")
    print(f"status={report['status']}")
    return 0 if report["status"] == "PASS" else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
