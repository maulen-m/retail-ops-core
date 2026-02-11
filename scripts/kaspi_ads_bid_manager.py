#!/usr/bin/env python3
"""Kaspi ads bid manager with strict dry-run defaults and write gating."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import yaml

try:
    from scripts.kaspi_ads_paths import (
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )
except ModuleNotFoundError:
    from kaspi_ads_paths import (  # type: ignore
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )

ALMATY_TZ = ZoneInfo("Asia/Almaty")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "kaspi_ads_bid_rules.yaml"
DEFAULT_DISCOVERY_PATH = PROJECT_ROOT / "docs" / "marketing" / "bid_api_discovery.json"


def _env_get(env: Mapping[str, str] | Any, key: str) -> str | None:
    getter = getattr(env, "get", None)
    if callable(getter):
        value = getter(key)
        return None if value is None else str(value)
    return None


def ensure_bid_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bid_change_log (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            old_bid REAL,
            new_bid REAL,
            rule_name TEXT,
            dry_run INTEGER NOT NULL DEFAULT 1,
            success INTEGER,
            error_message TEXT,
            method TEXT,
            reason TEXT
        )
        """
    )
    conn.commit()


def load_rules(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Rules config must be a mapping")
    return payload


def _load_discovery_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _current_multiplier(rules: dict[str, Any], hour: int) -> tuple[float, str]:
    schedules = rules.get("schedules") or []
    if not isinstance(schedules, list):
        return 1.0, "base"

    for item in schedules:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        start = int(item.get("start_hour", 0))
        end = int(item.get("end_hour", 24))
        if start <= hour < end:
            return float(item.get("multiplier", 1.0)), str(item.get("name", "schedule"))
    return 1.0, "base"


def _load_current_bids(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    row = conn.execute("SELECT MAX(date) FROM campaign_product_daily_current").fetchone()
    if not row or not row[0]:
        return []
    target_date = str(row[0])
    rows = conn.execute(
        """
        SELECT date, merchant_id, campaign_id, sku_key, COALESCE(bid_cpc, 0)
        FROM campaign_product_daily_current
        WHERE date = ?
        """,
        (target_date,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for date_value, merchant_id, campaign_id, sku_key, bid_cpc in rows:
        out.append(
            {
                "date": str(date_value),
                "merchant_id": str(merchant_id or ""),
                "campaign_id": str(campaign_id or ""),
                "sku_key": str(sku_key or ""),
                "bid_cpc": float(bid_cpc or 0.0),
            }
        )
    return out


def _daily_changes_count(conn: sqlite3.Connection, *, campaign_id: str, sku_key: str, day: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM bid_change_log
        WHERE campaign_id = ?
          AND sku_key = ?
          AND substr(executed_at, 1, 10) = ?
          AND COALESCE(success, 0) = 1
        """,
        (campaign_id, sku_key, day),
    ).fetchone()
    return int(row[0] if row else 0)


def _last_change_at(conn: sqlite3.Connection, *, campaign_id: str, sku_key: str) -> datetime | None:
    row = conn.execute(
        """
        SELECT executed_at
        FROM bid_change_log
        WHERE campaign_id = ?
          AND sku_key = ?
          AND COALESCE(success, 0) = 1
        ORDER BY change_id DESC
        LIMIT 1
        """,
        (campaign_id, sku_key),
    ).fetchone()
    if not row or not row[0]:
        return None
    raw = str(row[0])
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _last_successful_change(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    sku_key: str,
) -> tuple[float, float] | None:
    row = conn.execute(
        """
        SELECT old_bid, new_bid
        FROM bid_change_log
        WHERE campaign_id = ?
          AND sku_key = ?
          AND COALESCE(success, 0) = 1
        ORDER BY change_id DESC
        LIMIT 1
        """,
        (campaign_id, sku_key),
    ).fetchone()
    if not row:
        return None
    old_bid, new_bid = row
    return float(old_bid or 0.0), float(new_bid or 0.0)


def _log_change(
    conn: sqlite3.Connection,
    *,
    executed_at: str,
    campaign_id: str,
    sku_key: str,
    old_bid: float,
    new_bid: float,
    rule_name: str,
    dry_run: int,
    success: int,
    error_message: str,
    method: str,
    reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO bid_change_log (
            executed_at,
            campaign_id,
            sku_key,
            old_bid,
            new_bid,
            rule_name,
            dry_run,
            success,
            error_message,
            method,
            reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            executed_at,
            campaign_id,
            sku_key,
            round(float(old_bid), 4),
            round(float(new_bid), 4),
            rule_name,
            int(dry_run),
            int(success),
            error_message,
            method,
            reason,
        ),
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def _apply_step_cap(current_bid: float, target_bid: float, max_step: float) -> float:
    if max_step <= 0:
        return target_bid
    delta = target_bid - current_bid
    if abs(delta) <= max_step:
        return target_bid
    if delta > 0:
        return current_bid + max_step
    return current_bid - max_step


def execute_bid_manager(
    conn: sqlite3.Connection,
    *,
    rules: dict[str, Any],
    now_local: datetime,
    apply: bool,
    env: Mapping[str, str] | Any,
    discovery_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    ensure_bid_schema(conn)

    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=ALMATY_TZ)
    else:
        now_local = now_local.astimezone(ALMATY_TZ)

    safety = rules.get("safety") if isinstance(rules.get("safety"), dict) else {}
    min_bid = float(safety.get("min_bid_kzt", 10.0))
    max_bid = float(safety.get("max_bid_kzt", 200.0))
    max_step = float(safety.get("max_step_change_kzt", 30.0))
    max_daily_changes = int(safety.get("max_daily_changes", 2))
    cooldown_minutes = int(safety.get("cooldown_minutes", 60))
    require_env = str(safety.get("require_env", "ENABLE_KASPI_ADS_WRITE"))
    config_dry_run = bool(safety.get("dry_run", True))

    result: dict[str, Any] = {
        "exit_code": 0,
        "error": "",
        "proposed_changes": 0,
        "executed_changes": 0,
        "skipped_allowlist": 0,
        "skipped_no_change": 0,
        "skipped_daily_limit": 0,
        "skipped_cooldown": 0,
        "write_errors": 0,
    }

    env_allowed = _env_get(env, require_env) == "1"
    if apply and not env_allowed:
        return {
            **result,
            "exit_code": 1,
            "error": f"{require_env}=1 is required with --apply",
        }

    do_live_write = bool(apply and env_allowed and not config_dry_run)
    if do_live_write and not discovery_payload:
        return {
            **result,
            "exit_code": 1,
            "error": "Bid write API discovery payload is required for live writes.",
        }

    multiplier, rule_name = _current_multiplier(rules, now_local.hour)
    allowlist_pairs = {
        (str(item.get("campaign_id", "")), str(item.get("sku_key", "")))
        for item in (rules.get("allowlist") or [])
        if isinstance(item, dict)
    }
    campaigns_cfg = rules.get("campaigns") if isinstance(rules.get("campaigns"), dict) else {}

    executed_at = now_local.isoformat()
    day_str = now_local.date().isoformat()

    for row in _load_current_bids(conn):
        campaign_id = row["campaign_id"]
        sku_key = row["sku_key"]
        current_bid = float(row["bid_cpc"])

        if allowlist_pairs and (campaign_id, sku_key) not in allowlist_pairs:
            result["skipped_allowlist"] += 1
            continue

        campaign_cfg = campaigns_cfg.get(campaign_id, {}) if isinstance(campaigns_cfg.get(campaign_id), dict) else {}
        base_bid = float(campaign_cfg.get("base_bid", current_bid))

        target_bid = _clamp(base_bid * multiplier, min_bid, max_bid)
        target_bid = _apply_step_cap(current_bid, target_bid, max_step)
        target_bid = round(_clamp(target_bid, min_bid, max_bid), 4)

        if abs(target_bid - current_bid) < 1e-9:
            result["skipped_no_change"] += 1
            continue

        if _daily_changes_count(conn, campaign_id=campaign_id, sku_key=sku_key, day=day_str) >= max_daily_changes:
            result["skipped_daily_limit"] += 1
            continue

        last_change = _last_change_at(conn, campaign_id=campaign_id, sku_key=sku_key)
        if last_change is not None:
            elapsed_min = (now_local - last_change).total_seconds() / 60.0
            if elapsed_min < cooldown_minutes:
                result["skipped_cooldown"] += 1
                continue

        result["proposed_changes"] += 1
        if do_live_write:
            # Live write endpoint is intentionally stubbed until discovery payload
            # is fully validated in a controlled canary.
            _log_change(
                conn,
                executed_at=executed_at,
                campaign_id=campaign_id,
                sku_key=sku_key,
                old_bid=current_bid,
                new_bid=target_bid,
                rule_name=rule_name,
                dry_run=0,
                success=0,
                error_message="Live bid write not implemented in this phase",
                method="api",
                reason="write_error",
            )
            result["write_errors"] += 1
        else:
            _log_change(
                conn,
                executed_at=executed_at,
                campaign_id=campaign_id,
                sku_key=sku_key,
                old_bid=current_bid,
                new_bid=target_bid,
                rule_name=rule_name,
                dry_run=1,
                success=1,
                error_message="",
                method="none",
                reason="would_change",
            )

    conn.commit()
    if do_live_write and result["write_errors"] > 0:
        result["exit_code"] = 1
        result["error"] = "Live write attempted but failed; see bid_change_log."
    return result


def execute_bid_rollback(
    conn: sqlite3.Connection,
    *,
    rules: dict[str, Any],
    now_local: datetime,
    apply: bool,
    env: Mapping[str, str] | Any,
    discovery_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    ensure_bid_schema(conn)

    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=ALMATY_TZ)
    else:
        now_local = now_local.astimezone(ALMATY_TZ)

    safety = rules.get("safety") if isinstance(rules.get("safety"), dict) else {}
    require_env = str(safety.get("require_env", "ENABLE_KASPI_ADS_WRITE"))
    config_dry_run = bool(safety.get("dry_run", True))

    result: dict[str, Any] = {
        "exit_code": 0,
        "error": "",
        "rollback_candidates": 0,
        "rollback_applied": 0,
        "rollback_missing_history": 0,
        "write_errors": 0,
    }

    env_allowed = _env_get(env, require_env) == "1"
    if apply and not env_allowed:
        return {
            **result,
            "exit_code": 1,
            "error": f"{require_env}=1 is required with --apply",
        }

    do_live_write = bool(apply and env_allowed and not config_dry_run)
    if do_live_write and not discovery_payload:
        return {
            **result,
            "exit_code": 1,
            "error": "Bid write API discovery payload is required for live rollback writes.",
        }

    allowlist_pairs = {
        (str(item.get("campaign_id", "")), str(item.get("sku_key", "")))
        for item in (rules.get("allowlist") or [])
        if isinstance(item, dict)
    }
    executed_at = now_local.isoformat()

    for row in _load_current_bids(conn):
        campaign_id = row["campaign_id"]
        sku_key = row["sku_key"]
        current_bid = float(row["bid_cpc"])
        if allowlist_pairs and (campaign_id, sku_key) not in allowlist_pairs:
            continue

        hist = _last_successful_change(conn, campaign_id=campaign_id, sku_key=sku_key)
        if hist is None:
            result["rollback_missing_history"] += 1
            continue
        target_bid = round(float(hist[0]), 4)
        if abs(target_bid - current_bid) < 1e-9:
            continue

        result["rollback_candidates"] += 1
        if do_live_write:
            _log_change(
                conn,
                executed_at=executed_at,
                campaign_id=campaign_id,
                sku_key=sku_key,
                old_bid=current_bid,
                new_bid=target_bid,
                rule_name="rollback_last_good",
                dry_run=0,
                success=0,
                error_message="Live bid rollback write not implemented in this phase",
                method="api",
                reason="rollback_write_error",
            )
            result["write_errors"] += 1
        else:
            _log_change(
                conn,
                executed_at=executed_at,
                campaign_id=campaign_id,
                sku_key=sku_key,
                old_bid=current_bid,
                new_bid=target_bid,
                rule_name="rollback_last_good",
                dry_run=1,
                success=1,
                error_message="",
                method="none",
                reason="would_rollback",
            )
            result["rollback_applied"] += 1

    conn.commit()
    if do_live_write and result["write_errors"] > 0:
        result["exit_code"] = 1
        result["error"] = "Live rollback attempted but failed; see bid_change_log."
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kaspi ads bid manager (dry-run by default)")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--discovery-file", type=Path, default=DEFAULT_DISCOVERY_PATH)
    parser.add_argument("--apply", action="store_true", help="Attempt live writes (requires env gate)")
    parser.add_argument(
        "--rollback-last-good",
        action="store_true",
        help="Rollback to previous successful bids from bid_change_log history",
    )
    parser.add_argument("--now-local", default=None, help="Override current local time (ISO-8601)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ads_db = resolve_ads_db_path(ads_db_arg=args.ads_db, default_path=DEFAULT_WORKTREE_ADS_DB_PATH)
    assert_ads_db_path_safe(ads_db_path=ads_db)

    rules = load_rules(args.rules)
    discovery = _load_discovery_payload(args.discovery_file)
    now_local = datetime.fromisoformat(args.now_local) if args.now_local else datetime.now(ALMATY_TZ)

    with sqlite3.connect(ads_db) as conn:
        if args.rollback_last_good:
            summary = execute_bid_rollback(
                conn,
                rules=rules,
                now_local=now_local,
                apply=args.apply,
                env=os.environ,
                discovery_payload=discovery,
            )
        else:
            summary = execute_bid_manager(
                conn,
                rules=rules,
                now_local=now_local,
                apply=args.apply,
                env=os.environ,
                discovery_payload=discovery,
            )

    print(json.dumps({"ads_db": str(ads_db), **summary}, ensure_ascii=False))
    return int(summary.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
