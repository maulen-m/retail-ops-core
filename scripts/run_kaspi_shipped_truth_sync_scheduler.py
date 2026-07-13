#!/usr/bin/env python3
"""DB-only Kaspi shipped-truth sync.

This is intentionally narrower than the full CRM import path:
- no Excel workbook writes
- no Google Sheet publish
- no waybill / delivery sending

It refreshes fact_orders_kaspi lifecycle truth from Kaspi API states that can
carry courierTransmissionDate for recent shipped orders.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYNC_KASPI_ORDERS_PATH = PROJECT_ROOT / "scripts" / "sync_kaspi_orders.py"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "kaspi_shipped_truth_sync"
APPLY_GATE_ENV = "ENABLE_KASPI_SHIPPED_TRUTH_SYNC"
DEFAULT_STATES = ["KASPI_DELIVERY", "ARCHIVE"]
DEFAULT_LOOKBACK_DAYS = 13

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.google_ops_board_automation_common import (  # noqa: E402
    ALMATY_TZ,
    ensure_kaspi_api_call_ledger_env,
    today_almaty,
)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _parse_target_date(value: str | None) -> date:
    if not value:
        return today_almaty()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _db_shipped_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_path": str(db_path), "exists": False, "row_count": 0, "max_shipped_at": ""}
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    MAX(COALESCE(actual_shipment_date, courier_transmission_date, '')) AS max_shipped_at,
                    COUNT(*) AS row_count
                FROM fact_orders_kaspi
                WHERE COALESCE(actual_shipment_date, courier_transmission_date, '') != ''
                """
            ).fetchone()
    except sqlite3.Error as exc:
        return {"db_path": str(db_path), "exists": True, "error": str(exc), "row_count": 0, "max_shipped_at": ""}
    return {
        "db_path": str(db_path),
        "exists": True,
        "row_count": int(row[1] or 0) if row else 0,
        "max_shipped_at": str(row[0] or "") if row else "",
    }


def _default_json_out(target_date: date, output_root: Path) -> Path:
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    return output_root / target_date.isoformat() / f"kaspi_shipped_truth_sync_{stamp}.json"


def _build_sync_command(
    *,
    python_executable: str,
    target_date: date,
    lookback_days: int,
    states: list[str],
    db_path: Path,
    dry_run: bool,
) -> list[str]:
    since_date = target_date - timedelta(days=max(1, lookback_days) - 1)
    command = [
        python_executable,
        str(SYNC_KASPI_ORDERS_PATH),
        "--all",
        "--since",
        since_date.isoformat(),
        "--until",
        target_date.isoformat(),
        "--states",
        ",".join(states),
        "--db-path",
        str(db_path),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh DB shipped truth from Kaspi API without CRM/Google side effects.")
    parser.add_argument("--target-date", help="Target operational date YYYY-MM-DD. Defaults to today in Asia/Almaty.")
    parser.add_argument("--lookback-days", type=int, default=int(os.environ.get("KASPI_SHIPPED_TRUTH_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS)))
    parser.add_argument("--states", default=",".join(DEFAULT_STATES), help="Comma-separated Kaspi states to fetch.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--reason", default="scheduled")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    target_date = _parse_target_date(args.target_date)
    states = [part.strip() for part in str(args.states or "").split(",") if part.strip()]
    json_out = Path(args.json_out).expanduser() if args.json_out else _default_json_out(target_date, Path(args.output_root).expanduser())
    db_path = Path(args.db_path).expanduser()

    if not args.dry_run and os.environ.get(APPLY_GATE_ENV) != "1":
        report = {
            "ok": False,
            "reason": args.reason,
            "target_date": target_date.isoformat(),
            "returncode": 78,
            "error": f"{APPLY_GATE_ENV}=1 is required for DB shipped-truth sync",
        }
        _dump_json(json_out, report)
        print(report["error"], file=sys.stderr)
        return 78

    if not SYNC_KASPI_ORDERS_PATH.exists():
        print(f"ERROR: missing sync script: {SYNC_KASPI_ORDERS_PATH}", file=sys.stderr)
        return 78
    if not DB_CHECK_PATH.exists():
        print(f"ERROR: missing DB preflight script: {DB_CHECK_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    ensure_kaspi_api_call_ledger_env(env, target_date=target_date, project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    before = _db_shipped_summary(db_path)
    db_check_cmd = [sys.executable, str(DB_CHECK_PATH), "--db-path", str(db_path)]
    db_check = subprocess.run(db_check_cmd, cwd=str(PROJECT_ROOT), env=env, text=True, capture_output=True)
    if db_check.returncode != 0:
        report = {
            "ok": False,
            "reason": args.reason,
            "target_date": target_date.isoformat(),
            "states": states,
            "db_path": str(db_path),
            "before": before,
            "db_check": {
                "command": db_check_cmd,
                "returncode": int(db_check.returncode),
                "stdout": db_check.stdout,
                "stderr": db_check.stderr,
            },
            "returncode": int(db_check.returncode),
        }
        _dump_json(json_out, report)
        return int(db_check.returncode)

    command = _build_sync_command(
        python_executable=sys.executable,
        target_date=target_date,
        lookback_days=int(args.lookback_days),
        states=states,
        db_path=db_path,
        dry_run=bool(args.dry_run),
    )
    proc = subprocess.run(command, cwd=str(PROJECT_ROOT), env=env, text=True, capture_output=True)
    after = _db_shipped_summary(db_path)
    report = {
        "ok": int(proc.returncode) == 0,
        "reason": args.reason,
        "target_date": target_date.isoformat(),
        "lookback_days": int(args.lookback_days),
        "states": states,
        "db_path": str(db_path),
        "dry_run": bool(args.dry_run),
        "before": before,
        "after": after,
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ledger_path": env.get("KASPI_API_CALL_LEDGER_PATH", ""),
        "json_out": str(json_out),
    }
    _dump_json(json_out, report)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    print(f"Kaspi shipped-truth sync report: {json_out}")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
