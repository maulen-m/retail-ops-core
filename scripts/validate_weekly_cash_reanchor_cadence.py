#!/usr/bin/env python3
"""Validate the weekly cash re-anchor cadence without applying DB writes."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sync_cash_balances_from_inbound_calendar import _read_snapshot  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_WORKBOOK = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "weekly_cash_reanchor"


class WeeklyCashCadenceError(RuntimeError):
    """Raised when the weekly cash cadence cannot be evaluated."""


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_workbook_as_of(value: str) -> datetime:
    raw = str(value or "").replace(" GMT+5", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise WeeklyCashCadenceError(f"cannot parse workbook snapshot timestamp: {value!r}")


def _load_latest_anchor(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "cashflow_cash_anchor"):
        raise WeeklyCashCadenceError("cashflow_cash_anchor table missing")
    latest = conn.execute("SELECT MAX(anchor_date) AS anchor_date FROM cashflow_cash_anchor").fetchone()
    anchor_date = str(latest["anchor_date"] or "") if latest else ""
    if not anchor_date:
        raise WeeklyCashCadenceError("cashflow_cash_anchor has no anchor rows")

    row = conn.execute(
        """
        SELECT
            anchor_date,
            COUNT(*) AS anchor_rows,
            ROUND(SUM(COALESCE(anchor_closing_balance_kzt, 0)), 2) AS anchor_total_kzt,
            SUM(CASE WHEN COALESCE(source_store_name, '') LIKE 'RESERVE:%' THEN 1 ELSE 0 END)
                AS reserve_rows,
            MIN(created_by_run_id) AS min_run_id,
            MAX(created_by_run_id) AS max_run_id
        FROM cashflow_cash_anchor
        WHERE anchor_date=?
        GROUP BY anchor_date
        """,
        (anchor_date,),
    ).fetchone()
    if row is None:
        raise WeeklyCashCadenceError(f"latest anchor row disappeared: {anchor_date}")

    daily = None
    if _table_exists(conn, "fact_cashflow_daily"):
        daily = conn.execute(
            """
            SELECT date, ROUND(cash_close, 2) AS cash_close_kzt, run_id
            FROM fact_cashflow_daily
            WHERE date=?
            """,
            (anchor_date,),
        ).fetchone()

    return {
        "anchor_date": str(row["anchor_date"]),
        "anchor_rows": int(row["anchor_rows"] or 0),
        "anchor_total_kzt": float(row["anchor_total_kzt"] or 0.0),
        "reserve_rows": int(row["reserve_rows"] or 0),
        "min_run_id": str(row["min_run_id"] or ""),
        "max_run_id": str(row["max_run_id"] or ""),
        "daily_cash_close_kzt": float(daily["cash_close_kzt"] or 0.0) if daily else None,
        "daily_run_id": str(daily["run_id"] or "") if daily else None,
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Weekly Cash Re-anchor Cadence",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- max_age_days: `{report['max_age_days']}`",
        f"- workbook_snapshot_date: `{report['workbook']['snapshot_date']}`",
        f"- latest_anchor_date: `{report['anchor']['anchor_date']}`",
        f"- anchor_age_days: `{report['anchor']['anchor_age_days']}`",
        f"- workbook_snapshot_age_days: `{report['workbook']['snapshot_age_days']}`",
        f"- anchor_rows: `{report['anchor']['anchor_rows']}`",
        f"- anchor_total_kzt: `{report['anchor']['anchor_total_kzt']}`",
        f"- daily_cash_close_kzt: `{report['anchor']['daily_cash_close_kzt']}`",
    ]
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def validate_weekly_cash_reanchor_cadence(
    *,
    db_path: Path,
    workbook_path: Path,
    as_of: date,
    max_age_days: int,
    expected_anchor_rows: int,
    output_root: Path,
) -> dict[str, Any]:
    if max_age_days < 0:
        raise WeeklyCashCadenceError("max_age_days must be non-negative")
    if expected_anchor_rows <= 0:
        raise WeeklyCashCadenceError("expected_anchor_rows must be positive")
    if not db_path.exists():
        raise WeeklyCashCadenceError(f"DB not found: {db_path}")
    if not workbook_path.exists():
        raise WeeklyCashCadenceError(f"workbook not found: {workbook_path}")

    workbook_as_of, _balances, metadata = _read_snapshot(
        xlsx_path=workbook_path,
        sheet_name="Cash_Balances",
        snapshot_ts=None,
    )
    workbook_dt = _parse_workbook_as_of(workbook_as_of)
    workbook_date = workbook_dt.date()

    with _connect_readonly(db_path) as conn:
        anchor = _load_latest_anchor(conn)

    anchor_date = date.fromisoformat(anchor["anchor_date"])
    anchor_age_days = (as_of - anchor_date).days
    workbook_age_days = (as_of - workbook_date).days

    errors: list[str] = []
    if anchor_age_days < 0:
        errors.append(f"latest cash anchor is after as_of: anchor={anchor_date} as_of={as_of}")
    if workbook_age_days < 0:
        errors.append(
            f"latest workbook Cash_Balances snapshot is after as_of: snapshot={workbook_date} as_of={as_of}"
        )
    if anchor_age_days > max_age_days:
        errors.append(
            f"latest cash anchor is stale: age_days={anchor_age_days} max_age_days={max_age_days}"
        )
    if workbook_age_days > max_age_days:
        errors.append(
            "latest workbook Cash_Balances snapshot is stale: "
            f"age_days={workbook_age_days} max_age_days={max_age_days}"
        )
    if workbook_date > anchor_date:
        errors.append(
            f"workbook Cash_Balances snapshot {workbook_date} is newer than latest DB anchor {anchor_date}"
        )
    if int(anchor["anchor_rows"]) != int(expected_anchor_rows):
        errors.append(
            f"latest cash anchor row count mismatch: observed={anchor['anchor_rows']} "
            f"expected={expected_anchor_rows}"
        )
    if int(anchor["reserve_rows"]) != 0:
        errors.append(f"reserve rows leaked into operating cash anchor: {anchor['reserve_rows']}")
    daily_cash_close = anchor.get("daily_cash_close_kzt")
    if daily_cash_close is None:
        errors.append(f"fact_cashflow_daily missing latest anchor date {anchor_date}")
    elif abs(float(daily_cash_close) - float(anchor["anchor_total_kzt"])) > 0.01:
        errors.append(
            "fact_cashflow_daily cash_close does not match latest cash anchor: "
            f"cash_close={daily_cash_close} anchor_total={anchor['anchor_total_kzt']}"
        )

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": not errors,
        "errors": errors,
        "max_age_days": int(max_age_days),
        "expected_anchor_rows": int(expected_anchor_rows),
        "db_path": str(db_path.resolve()),
        "workbook": {
            "path": str(workbook_path.resolve()),
            "snapshot_as_of": workbook_as_of,
            "snapshot_date": workbook_date.isoformat(),
            "selected_label": str(metadata.get("selected_label") or ""),
            "selected_column": int(metadata.get("selected_column") or 0),
            "populated_cells": int(metadata.get("selected_populated_cells") or 0),
            "account_rows": int(metadata.get("account_rows") or 0),
            "snapshot_age_days": int(workbook_age_days),
        },
        "anchor": {
            **anchor,
            "anchor_age_days": int(anchor_age_days),
        },
    }

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "weekly_cash_reanchor_report.json"
    md_path = out_dir / "weekly_cash_reanchor_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate weekly cash re-anchor cadence")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--max-age-days", type=int, default=7)
    parser.add_argument("--expected-anchor-rows", type=int, default=18)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_weekly_cash_reanchor_cadence(
            db_path=args.db,
            workbook_path=args.workbook,
            as_of=date.fromisoformat(str(args.as_of)),
            max_age_days=int(args.max_age_days),
            expected_anchor_rows=int(args.expected_anchor_rows),
            output_root=args.output_root,
        )
    except WeeklyCashCadenceError as exc:
        print(f"ERROR: {exc}")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"weekly_cash_reanchor_report_json={report['json_path']}")
        print(f"status={report['status']}")
        print(f"latest_anchor_date={report['anchor']['anchor_date']}")
        print(f"workbook_snapshot_date={report['workbook']['snapshot_date']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
