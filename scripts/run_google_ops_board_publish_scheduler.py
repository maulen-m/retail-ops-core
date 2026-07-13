#!/usr/bin/env python3
"""LaunchAgent entrypoint for Google Ops Board publish schedule."""

from __future__ import annotations

import os
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_google_ops_board.py"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"
EXPORT_API_ORDERS_PATH = PROJECT_ROOT / "scripts" / "export_api_orders.py"
SYNC_KASPI_ORDERS_PATH = PROJECT_ROOT / "scripts" / "sync_kaspi_orders.py"
ENRICH_ACTIVEORDERS_PATH = PROJECT_ROOT / "scripts" / "enrich_kaspi_orders_from_activeorders.py"
VALIDATE_ACTIVEORDERS_COLUMNS_PATH = PROJECT_ROOT / "scripts" / "validate_activeorders_columns.py"
ACTIVEORDERS_PATH = PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "ActiveOrders.xlsx"
DEFAULT_SOURCE_SNAPSHOT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "source_snapshots"
ACTIVEORDERS_PLANNED_DATE_HEADER = "Плановая дата передачи курьеру"
DEFAULT_LOOKBACK_DAYS = 5
MORNING_SOURCE_REFRESH_HOUR = 7
MORNING_SOURCE_REFRESH_MINUTE = 0

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from scripts.google_ops_board_automation_common import (  # noqa: E402
    AUTOMATION_LOCK_HELD_ENV,
    GoogleOpsBoardAutomationLock,
    ensure_kaspi_api_call_ledger_env,
    now_almaty,
    today_almaty,
)
from scripts.run_google_ops_board_prewindow_health import ensure_prewindow_health  # noqa: E402

IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"
ACTIVEORDERS_DB_WRITE_ENV_GATE = "ENABLE_KASPI_ACTIVEORDERS_DB_WRITE"


def is_source_refresh_slot(now: datetime | None = None) -> bool:
    local_now = now or now_almaty()
    return local_now.hour == MORNING_SOURCE_REFRESH_HOUR and local_now.minute == MORNING_SOURCE_REFRESH_MINUTE


def inspect_activeorders_source(workbook_path: Path, *, target_date: date) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(workbook_path),
        "target_date": target_date.isoformat(),
        "target_label": target_date.strftime("%d.%m.%Y"),
        "exists": workbook_path.exists(),
        "mtime_date": "",
        "row_count": 0,
        "target_row_count": 0,
        "contains_target_date": False,
        "fresh": False,
        "planned_date_counts": {},
    }
    if not workbook_path.exists():
        return report

    stat = workbook_path.stat()
    report["mtime_date"] = datetime.fromtimestamp(stat.st_mtime, tz=now_almaty().tzinfo).date().isoformat()
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        worksheet = workbook.active
        headers = [str(cell) if cell is not None else "" for cell in next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))]
        if ACTIVEORDERS_PLANNED_DATE_HEADER not in headers:
            report["error"] = f"Missing required header: {ACTIVEORDERS_PLANNED_DATE_HEADER}"
            return report
        planned_date_idx = headers.index(ACTIVEORDERS_PLANNED_DATE_HEADER)
        target_label = report["target_label"]
        counts: Counter[str] = Counter()
        total_rows = 0
        target_rows = 0
        for row in worksheet.iter_rows(min_row=2, values_only=True):
            total_rows += 1
            planned_date = str(row[planned_date_idx] or "").strip()
            if not planned_date:
                continue
            counts[planned_date] += 1
            if planned_date == target_label:
                target_rows += 1
        report["row_count"] = total_rows
        report["target_row_count"] = target_rows
        report["contains_target_date"] = target_rows > 0
        report["planned_date_counts"] = dict(counts)
        # A successful current-day refresh may legitimately contain zero new
        # target-date orders. Freshness is the source observation date, not a
        # business-volume assertion; carryover obligations are added downstream.
        report["fresh"] = report["mtime_date"] == target_date.isoformat()
        return report
    except Exception as exc:
        report["error"] = str(exc)
        return report


def source_snapshot_path(target_date: date, *, snapshot_root: Path = DEFAULT_SOURCE_SNAPSHOT_ROOT) -> Path:
    return Path(snapshot_root) / target_date.isoformat() / "source_snapshot.json"


def build_file_fingerprint(path: Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "path": str(target),
            "exists": False,
            "size": 0,
            "mtime_ns": 0,
            "sha256": "",
        }
    stat = target.stat()
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(target),
        "exists": True,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": digest.hexdigest(),
    }


def write_source_snapshot(
    *,
    target_date: date,
    workbook_path: Path = ACTIVEORDERS_PATH,
    snapshot_root: Path = DEFAULT_SOURCE_SNAPSHOT_ROOT,
    refresh_slot: bool = False,
) -> dict[str, Any]:
    source_state = inspect_activeorders_source(workbook_path, target_date=target_date)
    if refresh_slot and source_state.get("contains_target_date"):
        source_state = dict(source_state)
        source_state["fresh"] = True
        source_state["freshness_basis"] = "refresh_slot_contains_target_date"
    path = source_snapshot_path(target_date, snapshot_root=snapshot_root)
    payload = {
        "target_date": target_date.isoformat(),
        "generated_at": now_almaty().isoformat(),
        "refresh_slot": bool(refresh_slot),
        "source_state": source_state,
        "source_fingerprint": build_file_fingerprint(workbook_path),
        "path": str(path),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def build_source_refresh_commands(
    *,
    target_date: date,
    workbook_path: Path,
    python_executable: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[list[str]]:
    since_date = (target_date - timedelta(days=lookback_days)).isoformat()
    return [
        [
            python_executable,
            str(EXPORT_API_ORDERS_PATH),
            "--all-stores",
            "--require-complete",
            "--state",
            "KASPI_DELIVERY",
            "--days",
            str(lookback_days),
            "--include-overdue",
            "--refetch-missing-costs",
            "--no-archive",
            "--output",
            str(workbook_path),
            "--verbose",
        ],
        [
            python_executable,
            str(VALIDATE_ACTIVEORDERS_COLUMNS_PATH),
            str(workbook_path),
        ],
        [
            python_executable,
            str(SYNC_KASPI_ORDERS_PATH),
            "--all",
            "--since",
            since_date,
            "-v",
        ],
        [
            python_executable,
            str(ENRICH_ACTIVEORDERS_PATH),
            "--apply",
            "--file",
            str(workbook_path),
            "--target-date",
            target_date.isoformat(),
        ],
    ]


def run_source_refresh(*, target_date: date, env: dict[str, str]) -> int:
    if not EXPORT_API_ORDERS_PATH.exists():
        print(f"ERROR: missing ActiveOrders exporter: {EXPORT_API_ORDERS_PATH}", file=sys.stderr)
        return 78
    if not SYNC_KASPI_ORDERS_PATH.exists():
        print(f"ERROR: missing Kaspi order sync script: {SYNC_KASPI_ORDERS_PATH}", file=sys.stderr)
        return 78
    if not ENRICH_ACTIVEORDERS_PATH.exists():
        print(f"ERROR: missing ActiveOrders enrichment script: {ENRICH_ACTIVEORDERS_PATH}", file=sys.stderr)
        return 78
    if not VALIDATE_ACTIVEORDERS_COLUMNS_PATH.exists():
        print(f"ERROR: missing ActiveOrders validator: {VALIDATE_ACTIVEORDERS_COLUMNS_PATH}", file=sys.stderr)
        return 78

    lookback_days = int(str(env.get("KASPI_LOOKBACK_DAYS") or DEFAULT_LOOKBACK_DAYS).strip() or DEFAULT_LOOKBACK_DAYS)
    commands = build_source_refresh_commands(
        target_date=target_date,
        workbook_path=ACTIVEORDERS_PATH,
        python_executable=sys.executable,
        lookback_days=lookback_days,
    )
    refresh_env = env.copy()
    refresh_env.setdefault(ACTIVEORDERS_DB_WRITE_ENV_GATE, "1")
    os.environ.setdefault(ACTIVEORDERS_DB_WRITE_ENV_GATE, refresh_env[ACTIVEORDERS_DB_WRITE_ENV_GATE])

    labels = (
        "Refreshing ActiveOrders export from live Kaspi API...",
        "Validating refreshed ActiveOrders workbook...",
        "Syncing DB order headers from Kaspi API...",
        "Enriching DB order identities from refreshed ActiveOrders workbook...",
    )
    for label, command in zip(labels, commands):
        print(label)
        result = subprocess.run(command, cwd=str(PROJECT_ROOT), env=refresh_env)
        if result.returncode != 0:
            print(f"ERROR: source refresh step failed: {label}", file=sys.stderr)
            return int(result.returncode)
    snapshot = write_source_snapshot(target_date=target_date, workbook_path=ACTIVEORDERS_PATH, refresh_slot=True)
    print(f"Source snapshot: {snapshot['path']}")
    return 0


def run_publish_cycle(*, env: dict[str, str], service_account_json: str, spreadsheet_id: str) -> int:
    target_date = today_almaty()
    ensure_kaspi_api_call_ledger_env(env, target_date=target_date, project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    check_cmd = [
        sys.executable,
        str(DB_CHECK_PATH),
        "--db-path",
        str(PROJECT_ROOT / "db" / "app.db"),
    ]
    check = subprocess.run(check_cmd, cwd=str(PROJECT_ROOT), env=env)
    if check.returncode != 0:
        print("ERROR: local DB preflight failed; skipping Google Ops Board publish.", file=sys.stderr)
        return int(check.returncode)

    if is_source_refresh_slot():
        print("07:00 publish slot detected; running full ActiveOrders -> DB source refresh before publish.")
        refresh_rc = run_source_refresh(target_date=target_date, env=env)
        if refresh_rc != 0:
            return int(refresh_rc)

    source_state = inspect_activeorders_source(ACTIVEORDERS_PATH, target_date=target_date)
    snapshot = write_source_snapshot(
        target_date=target_date,
        workbook_path=ACTIVEORDERS_PATH,
        refresh_slot=is_source_refresh_slot(),
    )
    print(f"Source snapshot: {snapshot['path']}")
    if not source_state.get("fresh"):
        print(
            "ERROR: ActiveOrders source is stale for target date; skipping Google Ops Board publish. "
            f"Source: {source_state.get('path', '')} "
            f"mtime_date={source_state.get('mtime_date', '')} "
            f"target_row_count={source_state.get('target_row_count', 0)}",
            file=sys.stderr,
        )
        return 1

    health = ensure_prewindow_health(
        target_date=target_date,
        db_path=PROJECT_ROOT / "db" / "app.db",
        contract_path=DEFAULT_CONTRACT_PATH,
        service_account_json=Path(service_account_json),
        spreadsheet_id=spreadsheet_id,
        apply=True,
        reason="publish_scheduler",
        profile="publish",
    )
    if not health.get("ok"):
        print(
            f"ERROR: prewindow health gate is red; skipping Google Ops Board publish. "
            f"Report: {health.get('report_path', '')}",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, str(SCRIPT_PATH), "--apply"]
    cmd.extend(["--spreadsheet-id", spreadsheet_id])
    cmd.extend(["--service-account-json", service_account_json])
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return int(result.returncode)


def main() -> int:
    if not SCRIPT_PATH.exists():
        print(f"ERROR: missing Google Ops Board publisher: {SCRIPT_PATH}", file=sys.stderr)
        return 78
    if not DB_CHECK_PATH.exists():
        print(f"ERROR: missing DB preflight script: {DB_CHECK_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault(IDENTITY_SYNC_WRITE_ENV_GATE, "1")
    os.environ.setdefault(IDENTITY_SYNC_WRITE_ENV_GATE, env[IDENTITY_SYNC_WRITE_ENV_GATE])

    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    try:
        service_account_path = resolve_service_account_json(contract=contract)
    except Exception:
        service_account_path = None
    service_account_json = str(service_account_path or "").strip()
    if not service_account_json or not Path(service_account_json).exists():
        print("ERROR: AB_GOOGLE_SERVICE_ACCOUNT_JSON is missing or does not exist.", file=sys.stderr)
        return 78
    spreadsheet_id = resolve_spreadsheet_id(
        str(env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") or "").strip() or None,
        contract=contract,
    )

    if str(os.environ.get(AUTOMATION_LOCK_HELD_ENV) or "").strip() == "1":
        env[AUTOMATION_LOCK_HELD_ENV] = "1"
        return run_publish_cycle(
            env=env,
            service_account_json=service_account_json,
            spreadsheet_id=spreadsheet_id,
        )

    previous_lock_env = os.environ.get(AUTOMATION_LOCK_HELD_ENV)
    try:
        with GoogleOpsBoardAutomationLock():
            os.environ[AUTOMATION_LOCK_HELD_ENV] = "1"
            env[AUTOMATION_LOCK_HELD_ENV] = "1"
            return run_publish_cycle(
                env=env,
                service_account_json=service_account_json,
                spreadsheet_id=spreadsheet_id,
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 0
    finally:
        if previous_lock_env is None:
            os.environ.pop(AUTOMATION_LOCK_HELD_ENV, None)
        else:
            os.environ[AUTOMATION_LOCK_HELD_ENV] = previous_lock_env


if __name__ == "__main__":
    raise SystemExit(main())
