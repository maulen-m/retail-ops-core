#!/usr/bin/env python3
"""Kaspi ads telemetry healthcheck: freshness and reconciliation drift."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from scripts.kaspi_ads_hourly_pipeline import DEFAULT_STORES_CONFIG, load_store_targets
    from scripts.kaspi_ads_paths import (
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )
except ModuleNotFoundError:
    from kaspi_ads_hourly_pipeline import DEFAULT_STORES_CONFIG, load_store_targets  # type: ignore
    from kaspi_ads_paths import (  # type: ignore
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )

ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(ALMATY_TZ).replace(tzinfo=None)
    return parsed


def _parse_store_targets(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.merchant_ids:
        merchant_ids = [item.strip() for item in str(args.merchant_ids).split(",") if item.strip()]
        return [
            {"store_code": f"MERCHANT_{merchant_id}", "merchant_id": merchant_id}
            for merchant_id in merchant_ids
        ]
    if args.merchant_id:
        merchant_id = str(args.merchant_id).strip()
        if merchant_id:
            return [{"store_code": f"MERCHANT_{merchant_id}", "merchant_id": merchant_id}]
    return load_store_targets(args.stores_config)


def _load_reconciliation_window(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT computed_at, within_tolerance, pct_diff
        FROM hourly_reconciliation
        WHERE merchant_id = ?
        """,
        (merchant_id,),
    ).fetchall()

    total = 0
    failures = 0
    pct_diffs: list[float] = []
    for computed_at, within_tolerance, pct_diff in rows:
        ts = _parse_dt(computed_at)
        if ts is None:
            continue
        if ts < start_at or ts >= end_at:
            continue
        total += 1
        if int(within_tolerance or 0) == 0:
            failures += 1
        pct_diffs.append(abs(float(pct_diff or 0.0)))

    fail_rate = (failures / total) if total else 0.0
    avg_abs_pct_diff = (sum(pct_diffs) / len(pct_diffs)) if pct_diffs else 0.0
    return {
        "rows": float(total),
        "failures": float(failures),
        "fail_rate": fail_rate,
        "avg_abs_pct_diff": avg_abs_pct_diff,
    }


def run_healthcheck(
    conn: sqlite3.Connection,
    *,
    store_targets: list[dict[str, str]],
    now_local: datetime | None = None,
    max_stale_hours: float = 2.0,
    recon_window_hours: int = 24,
    max_recon_fail_rate: float = 0.5,
    max_recon_avg_pct_diff: float = 15.0,
    max_recon_fail_rate_regression: float = 0.1,
    max_recon_avg_pct_diff_regression: float = 5.0,
    require_recon_rows: bool = False,
) -> dict[str, Any]:
    now_value = now_local or datetime.now(ALMATY_TZ).replace(tzinfo=None)
    failures: list[str] = []
    warnings: list[str] = []
    freshness_checks: list[dict[str, Any]] = []
    reconciliation_checks: list[dict[str, Any]] = []

    if not store_targets:
        failures.append("No enabled store targets resolved for healthcheck.")

    if not _table_exists(conn, "hourly_snapshot"):
        failures.append("Missing required table: hourly_snapshot.")
    if not _table_exists(conn, "hourly_reconciliation"):
        failures.append("Missing required table: hourly_reconciliation.")

    for target in store_targets:
        store_code = str(target.get("store_code", "")).strip() or "UNKNOWN"
        merchant_id = str(target.get("merchant_id", "")).strip()
        if not merchant_id:
            failures.append(f"{store_code}: missing merchant_id in store target.")
            continue

        latest_snapshot_row = None
        latest_snapshot_at = None
        stale_hours = None
        freshness_status = "unknown"

        if _table_exists(conn, "hourly_snapshot"):
            latest_snapshot_row = conn.execute(
                """
                SELECT snapshot_at
                FROM hourly_snapshot
                WHERE merchant_id = ?
                ORDER BY snapshot_at DESC
                LIMIT 1
                """,
                (merchant_id,),
            ).fetchone()

        if latest_snapshot_row is None:
            freshness_status = "missing"
            failures.append(
                f"{store_code} ({merchant_id}): no hourly_snapshot rows found."
            )
        else:
            latest_snapshot_at = _parse_dt(latest_snapshot_row[0])
            if latest_snapshot_at is None:
                freshness_status = "invalid_timestamp"
                failures.append(
                    f"{store_code} ({merchant_id}): could not parse latest snapshot_at={latest_snapshot_row[0]!r}."
                )
            else:
                stale_hours = max((now_value - latest_snapshot_at).total_seconds() / 3600.0, 0.0)
                freshness_status = "ok" if stale_hours <= max_stale_hours else "stale"
                if freshness_status != "ok":
                    failures.append(
                        f"{store_code} ({merchant_id}) stale snapshot: {stale_hours:.2f}h old > {max_stale_hours:.2f}h."
                    )

        freshness_checks.append(
            {
                "store_code": store_code,
                "merchant_id": merchant_id,
                "latest_snapshot_at": latest_snapshot_at.isoformat() if latest_snapshot_at else None,
                "stale_hours": stale_hours,
                "max_stale_hours": max_stale_hours,
                "status": freshness_status,
            }
        )

        recent_start = now_value - timedelta(hours=recon_window_hours)
        previous_start = now_value - timedelta(hours=recon_window_hours * 2)
        recent_stats = {
            "rows": 0.0,
            "failures": 0.0,
            "fail_rate": 0.0,
            "avg_abs_pct_diff": 0.0,
        }
        previous_stats = {
            "rows": 0.0,
            "failures": 0.0,
            "fail_rate": 0.0,
            "avg_abs_pct_diff": 0.0,
        }
        recon_status = "ok"

        if _table_exists(conn, "hourly_reconciliation"):
            recent_stats = _load_reconciliation_window(
                conn,
                merchant_id=merchant_id,
                start_at=recent_start,
                end_at=now_value,
            )
            previous_stats = _load_reconciliation_window(
                conn,
                merchant_id=merchant_id,
                start_at=previous_start,
                end_at=recent_start,
            )

            if int(recent_stats["rows"]) == 0:
                recon_status = "missing_recent_window"
                message = (
                    f"{store_code} ({merchant_id}): no hourly_reconciliation rows in last {recon_window_hours}h."
                )
                if require_recon_rows:
                    failures.append(message)
                else:
                    warnings.append(message)
            else:
                if recent_stats["fail_rate"] > max_recon_fail_rate:
                    recon_status = "above_fail_rate_threshold"
                    failures.append(
                        f"{store_code} ({merchant_id}) reconciliation fail_rate={recent_stats['fail_rate']:.3f} "
                        f"exceeds {max_recon_fail_rate:.3f}."
                    )
                if recent_stats["avg_abs_pct_diff"] > max_recon_avg_pct_diff:
                    recon_status = "above_pct_diff_threshold"
                    failures.append(
                        f"{store_code} ({merchant_id}) reconciliation avg_abs_pct_diff="
                        f"{recent_stats['avg_abs_pct_diff']:.2f}% exceeds {max_recon_avg_pct_diff:.2f}%."
                    )

            if int(previous_stats["rows"]) > 0 and int(recent_stats["rows"]) > 0:
                fail_rate_delta = recent_stats["fail_rate"] - previous_stats["fail_rate"]
                avg_pct_diff_delta = recent_stats["avg_abs_pct_diff"] - previous_stats["avg_abs_pct_diff"]
                if fail_rate_delta > max_recon_fail_rate_regression:
                    recon_status = "regression"
                    failures.append(
                        f"{store_code} ({merchant_id}) reconciliation regression: fail_rate delta="
                        f"{fail_rate_delta:.3f} > {max_recon_fail_rate_regression:.3f}."
                    )
                if avg_pct_diff_delta > max_recon_avg_pct_diff_regression:
                    recon_status = "regression"
                    failures.append(
                        f"{store_code} ({merchant_id}) reconciliation regression: avg_abs_pct_diff delta="
                        f"{avg_pct_diff_delta:.2f}% > {max_recon_avg_pct_diff_regression:.2f}%."
                    )
        else:
            recon_status = "missing_table"

        reconciliation_checks.append(
            {
                "store_code": store_code,
                "merchant_id": merchant_id,
                "window_hours": recon_window_hours,
                "recent": {
                    "rows": int(recent_stats["rows"]),
                    "failures": int(recent_stats["failures"]),
                    "fail_rate": round(float(recent_stats["fail_rate"]), 6),
                    "avg_abs_pct_diff": round(float(recent_stats["avg_abs_pct_diff"]), 6),
                },
                "previous": {
                    "rows": int(previous_stats["rows"]),
                    "failures": int(previous_stats["failures"]),
                    "fail_rate": round(float(previous_stats["fail_rate"]), 6),
                    "avg_abs_pct_diff": round(float(previous_stats["avg_abs_pct_diff"]), 6),
                },
                "status": recon_status,
            }
        )

    ok = len(failures) == 0
    return {
        "status": "ok" if ok else "error",
        "ok": ok,
        "checked_at": now_value.isoformat(),
        "max_stale_hours": max_stale_hours,
        "reconciliation_window_hours": recon_window_hours,
        "stores": store_targets,
        "freshness": freshness_checks,
        "reconciliation": reconciliation_checks,
        "failures": failures,
        "warnings": warnings,
        "exit_code": 0 if ok else 1,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kaspi ads telemetry healthcheck (freshness + reconciliation drift)."
    )
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH).")
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--merchant-id", default=None, help="Single merchant id override.")
    parser.add_argument("--merchant-ids", default=None, help="Comma-separated merchant ids override.")
    parser.add_argument("--max-stale-hours", type=float, default=2.0)
    parser.add_argument("--recon-window-hours", type=int, default=24)
    parser.add_argument("--max-recon-fail-rate", type=float, default=0.5)
    parser.add_argument("--max-recon-avg-pct-diff", type=float, default=15.0)
    parser.add_argument("--max-recon-fail-rate-regression", type=float, default=0.1)
    parser.add_argument("--max-recon-avg-pct-diff-regression", type=float, default=5.0)
    parser.add_argument("--require-recon-rows", action="store_true")
    parser.add_argument("--now", default=None, help="Override current local time (ISO-8601).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now_local = _parse_dt(args.now) if args.now else None
    if args.now and now_local is None:
        print(json.dumps({"status": "error", "error": f"Invalid --now value: {args.now!r}"}))
        return 2

    store_targets = _parse_store_targets(args)
    ads_db_path = resolve_ads_db_path(
        ads_db_arg=args.ads_db,
        default_path=DEFAULT_WORKTREE_ADS_DB_PATH,
    )
    assert_ads_db_path_safe(ads_db_path=ads_db_path)

    with sqlite3.connect(ads_db_path) as conn:
        result = run_healthcheck(
            conn,
            store_targets=store_targets,
            now_local=now_local,
            max_stale_hours=args.max_stale_hours,
            recon_window_hours=args.recon_window_hours,
            max_recon_fail_rate=args.max_recon_fail_rate,
            max_recon_avg_pct_diff=args.max_recon_avg_pct_diff,
            max_recon_fail_rate_regression=args.max_recon_fail_rate_regression,
            max_recon_avg_pct_diff_regression=args.max_recon_avg_pct_diff_regression,
            require_recon_rows=args.require_recon_rows,
        )
    result["ads_db"] = str(ads_db_path)
    print(json.dumps(result, ensure_ascii=False))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
