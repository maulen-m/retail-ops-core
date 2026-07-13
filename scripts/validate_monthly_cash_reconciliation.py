#!/usr/bin/env python3
"""Validate monthly economics reconciliation against cashflow events."""

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "cash_reconciliation"
DEFAULT_STATUSDATE_CUTOVER = date(2026, 2, 27)


class CashReconciliationError(RuntimeError):
    """Raised when strict cash reconciliation fails."""


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _object_exists(conn: sqlite3.Connection, object_type: str, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
            (object_type, name),
        ).fetchone()
        is not None
    )


def _paths_collide(left: Path, right: Path) -> bool:
    left_resolved = left.expanduser().resolve()
    right_resolved = right.expanduser().resolve()
    if left_resolved == right_resolved:
        return True
    try:
        return left_resolved.exists() and right_resolved.exists() and left_resolved.samefile(right_resolved)
    except OSError:
        return False


def _month_end(month_key: str) -> date:
    y, m = month_key.split("-")
    yy, mm = int(y), int(m)
    return date(yy, mm, monthrange(yy, mm)[1])


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Monthly Cash Reconciliation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- range: `{report['since']} -> {report['until']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- tolerance_pct: `{report['tolerance_pct']}`",
        f"- statusdate_cutover: `{report['statusdate_cutover']}`",
        f"- covered_pairs: `{report['covered_pairs']}`",
        "",
        "| month | store | decision_grade | covered | db_net_rev | cash_net_rev | rel_diff_pct |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['sale_month']}` | `{row['store_code']}` | `{str(row['decision_grade']).lower()}` | "
            f"`{str(row['covered']).lower()}` | {row['db_net_rev_kzt']:.2f} | {row['cash_net_rev_kzt']:.2f} | {row['rel_diff_pct']:.2f} |"
        )

    if report["mismatches"]:
        lines.extend(["", "## Mismatches", ""])
        for msg in report["mismatches"]:
            lines.append(f"- {msg}")

    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def validate_monthly_cash_reconciliation(
    *,
    db_path: Path,
    since: date,
    until: date,
    output_root: Path,
    tolerance_pct: float,
    statusdate_cutover: date,
    require_covered_pairs: bool,
    strict: bool,
) -> dict[str, Any]:
    if until < since:
        raise CashReconciliationError("until must be >= since")
    if tolerance_pct < 0:
        raise CashReconciliationError("tolerance_pct must be >= 0")
    if not db_path.exists():
        raise CashReconciliationError(f"db not found: {db_path}")

    db_path = db_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if _paths_collide(output_root, db_path):
        raise CashReconciliationError("output_root must not resolve to the DB path or a hardlink to it")
    if db_path != DEFAULT_DB.expanduser().resolve() and output_root == DEFAULT_OUTPUT_ROOT.expanduser().resolve():
        raise CashReconciliationError(
            "non-production DB requires an explicit noncanonical output_root"
        )

    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _object_exists(conn, "view", "view_sales_line_truth"):
            raise CashReconciliationError(
                "required view missing: view_sales_line_truth; prepare schema in a separately write-gated lane"
            )
        if not _object_exists(conn, "table", "fact_cashflow_events"):
            raise CashReconciliationError("required table missing: fact_cashflow_events")
        sales = pd.read_sql_query(
            """
            SELECT
                substr(date(sale_date), 1, 7) AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(COALESCE(net_rev_kzt, 0)) AS db_net_rev_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY substr(date(sale_date), 1, 7), UPPER(COALESCE(store_code, 'UNKNOWN'))
            """,
            conn,
            params=(since.isoformat(), until.isoformat()),
        )

        events = pd.read_sql_query(
            """
            SELECT
                substr(date(event_date), 1, 7) AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(CASE WHEN event_type='SALE_ACCRUED' THEN COALESCE(amount_kzt,0) ELSE 0 END) AS sale_accrued_kzt,
                SUM(CASE WHEN event_type='REFUND' THEN COALESCE(amount_kzt,0) ELSE 0 END) AS refund_kzt,
                COUNT(DISTINCT date(event_date)) AS event_days
            FROM fact_cashflow_events
            WHERE date(event_date) BETWEEN ? AND ?
            GROUP BY substr(date(event_date), 1, 7), UPPER(COALESCE(store_code, 'UNKNOWN'))
            """,
            conn,
            params=(since.isoformat(), until.isoformat()),
        )
    finally:
        conn.close()

    merged = sales.merge(events, on=["sale_month", "store_code"], how="outer").fillna(0)
    merged = merged.sort_values(["sale_month", "store_code"]).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    notes: list[str] = []
    covered_pairs = 0

    for _, raw in merged.iterrows():
        month = str(raw.get("sale_month") or "")
        if not month:
            continue
        store = str(raw.get("store_code") or "UNKNOWN").upper()
        db_net = _safe_float(raw.get("db_net_rev_kzt"))
        sale_accrued = _safe_float(raw.get("sale_accrued_kzt"))
        refund = _safe_float(raw.get("refund_kzt"))
        cash_net = sale_accrued + refund
        event_days = int(round(_safe_float(raw.get("event_days"))))

        month_end = _month_end(month)
        closed_month = month_end < until
        decision_grade = bool(closed_month and month_end >= statusdate_cutover)

        covered = bool(decision_grade and event_days > 0 and abs(cash_net) > 0.0)
        if covered:
            covered_pairs += 1

        denom = max(abs(db_net), 1.0)
        rel_diff = abs(db_net - cash_net) / denom
        rel_diff_pct = round(rel_diff * 100.0, 4)
        exceeds = bool(covered and rel_diff > tolerance_pct)
        if exceeds:
            mismatches.append(
                f"{month} {store}: db_net={db_net:.2f} cash_net={cash_net:.2f} rel_diff_pct={rel_diff_pct:.2f}"
            )

        rows.append(
            {
                "sale_month": month,
                "store_code": store,
                "db_net_rev_kzt": round(db_net, 2),
                "sale_accrued_kzt": round(sale_accrued, 2),
                "refund_kzt": round(refund, 2),
                "cash_net_rev_kzt": round(cash_net, 2),
                "event_days": event_days,
                "closed_month": closed_month,
                "decision_grade": decision_grade,
                "covered": covered,
                "rel_diff_pct": rel_diff_pct,
                "exceeds_tolerance": exceeds,
            }
        )

    if covered_pairs == 0:
        notes.append(
            "No covered decision-grade month/store pairs available for strict cash reconciliation in this window."
        )

    errors: list[str] = []
    error_codes: list[str] = []
    if mismatches:
        error_codes.append("CASH_RECON_MISMATCH")
        errors.append(f"{len(mismatches)} covered pair(s) exceed tolerance")
    if require_covered_pairs and covered_pairs == 0:
        error_codes.append("CASH_RECON_NO_COVERAGE")
        errors.append("no covered decision-grade month/store pairs available")

    out_dir = output_root.resolve() / until.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_csv = out_dir / "cash_reconciliation_rows.csv"
    pd.DataFrame(rows).to_csv(rows_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "mismatches": mismatches,
        "notes": notes,
        "rows": rows,
        "covered_pairs": covered_pairs,
        "tolerance_pct": float(tolerance_pct),
        "statusdate_cutover": statusdate_cutover.isoformat(),
        "db_path": str(db_path.resolve()),
        "db_open_mode": "read_only",
        "rows_csv": str(rows_csv),
    }

    json_path = out_dir / "cash_reconciliation_report.json"
    md_path = out_dir / "cash_reconciliation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise CashReconciliationError("cash reconciliation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate monthly economics against cashflow events")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default="2025-06-06")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--tolerance-pct", type=float, default=0.25)
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER.isoformat())
    parser.add_argument("--require-covered-pairs", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_monthly_cash_reconciliation(
            db_path=args.db,
            since=date.fromisoformat(str(args.since)),
            until=date.fromisoformat(str(args.as_of)),
            output_root=args.output_root,
            tolerance_pct=float(args.tolerance_pct),
            statusdate_cutover=date.fromisoformat(str(args.statusdate_cutover)),
            require_covered_pairs=bool(args.require_covered_pairs),
            strict=bool(args.strict),
        )
    except CashReconciliationError as exc:
        print("status=FAIL")
        print("error_code=CASH_RECON_FAIL")
        print(f"message={exc}")
        return 1

    print(f"cash_reconciliation_json={report['json_path']}")
    print(f"cash_reconciliation_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
