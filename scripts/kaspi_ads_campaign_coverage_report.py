#!/usr/bin/env python3
"""Kaspi ads coverage report for campaigns/products over a recent lookback window."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MARKETING_DOCS = PROJECT_ROOT / "docs" / "marketing"
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


def discover_inventory_json_files(marketing_docs_dir: Path = DEFAULT_MARKETING_DOCS) -> list[Path]:
    if not marketing_docs_dir.exists():
        return []
    candidates = sorted(marketing_docs_dir.glob("*campaign_inventory*.json"))
    return candidates


def load_expected_campaigns(
    inventory_paths: list[Path],
) -> tuple[dict[str, set[str]], list[str]]:
    expected: dict[str, set[str]] = defaultdict(set)
    warnings: list[str] = []

    for path in inventory_paths:
        if not path.exists():
            warnings.append(f"Expected inventory JSON missing: {path}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            warnings.append(f"Invalid JSON in {path}: {exc}")
            continue
        if not isinstance(payload, dict):
            warnings.append(f"Invalid inventory structure in {path}: expected object root.")
            continue

        store_code = str(payload.get("store_code", "")).strip()
        merchant_id = str(payload.get("merchant_id", "")).strip()
        enabled_campaigns = payload.get("enabled_campaigns")
        if not isinstance(enabled_campaigns, list):
            warnings.append(f"Inventory file has no enabled_campaigns list: {path}")
            continue

        campaign_ids = {
            str(item.get("campaign_id", "")).strip()
            for item in enabled_campaigns
            if isinstance(item, dict) and str(item.get("campaign_id", "")).strip()
        }
        if not campaign_ids:
            continue
        if store_code:
            expected[store_code].update(campaign_ids)
        if merchant_id:
            expected[merchant_id].update(campaign_ids)

    return expected, warnings


def infer_expected_campaigns_from_latest_snapshot(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
) -> set[str]:
    latest_row = conn.execute(
        """
        SELECT date
        FROM hourly_snapshot
        WHERE merchant_id = ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (merchant_id,),
    ).fetchone()
    if latest_row is None or not latest_row[0]:
        return set()
    latest_date = str(latest_row[0])
    rows = conn.execute(
        """
        SELECT DISTINCT campaign_id
        FROM hourly_snapshot
        WHERE merchant_id = ? AND date = ?
        """,
        (merchant_id, latest_date),
    ).fetchall()
    return {str(row[0]).strip() for row in rows if row and str(row[0]).strip()}


def _build_acmewear_rows_one_note(
    *,
    rows_24h: int,
    expected_campaigns: set[str],
    missing_expected: list[str],
    stale_hours: float | None,
    max_stale_hours: float,
) -> tuple[str, str]:
    if rows_24h != 1:
        return "n/a", "ACMEWEAR rows=1 check not applicable."

    invalid_reasons: list[str] = []
    if stale_hours is None:
        invalid_reasons.append("latest snapshot is missing")
    elif stale_hours > max_stale_hours:
        invalid_reasons.append(
            f"latest snapshot is stale ({stale_hours:.2f}h > {max_stale_hours:.2f}h)"
        )
    if missing_expected:
        invalid_reasons.append(f"missing expected campaigns: {', '.join(missing_expected)}")
    if len(expected_campaigns) > 1:
        invalid_reasons.append(f"expected campaign count is {len(expected_campaigns)} (>1)")

    if invalid_reasons:
        return "invalid", "ACMEWEAR rows=1 is invalid: " + "; ".join(invalid_reasons) + "."
    return "valid", "ACMEWEAR rows=1 is valid: expected campaign count is 1 and coverage is complete."


def build_campaign_coverage_report(
    conn: sqlite3.Connection,
    *,
    store_targets: list[dict[str, str]],
    expected_campaigns_by_store: dict[str, set[str]],
    now_local: datetime | None = None,
    lookback_hours: int = 24,
    max_stale_hours: float = 2.0,
) -> dict[str, Any]:
    now_value = now_local or datetime.now(ALMATY_TZ).replace(tzinfo=None)
    lookback_start = now_value - timedelta(hours=lookback_hours)
    failures: list[str] = []
    stores_report: list[dict[str, Any]] = []

    if not store_targets:
        failures.append("No enabled store targets resolved for campaign coverage.")
    if not _table_exists(conn, "hourly_snapshot"):
        failures.append("Missing required table: hourly_snapshot.")

    for target in store_targets:
        store_code = str(target.get("store_code", "")).strip() or "UNKNOWN"
        merchant_id = str(target.get("merchant_id", "")).strip()
        if not merchant_id:
            failures.append(f"{store_code}: missing merchant_id in store target.")
            continue

        expected_campaigns = set(expected_campaigns_by_store.get(store_code, set()))
        expected_source = "inventory_json"
        if not expected_campaigns:
            expected_campaigns = set(expected_campaigns_by_store.get(merchant_id, set()))
            if expected_campaigns:
                expected_source = "inventory_json_by_merchant"
        if not expected_campaigns and _table_exists(conn, "hourly_snapshot"):
            inferred = infer_expected_campaigns_from_latest_snapshot(conn, merchant_id=merchant_id)
            expected_campaigns = set(inferred)
            expected_source = "db_latest_snapshot_inferred"

        rows = []
        if _table_exists(conn, "hourly_snapshot"):
            rows = conn.execute(
                """
                SELECT snapshot_at, campaign_id, sku_key
                FROM hourly_snapshot
                WHERE merchant_id = ?
                """,
                (merchant_id,),
            ).fetchall()

        rows_24h = 0
        campaigns_seen: set[str] = set()
        sku_seen: set[str] = set()
        campaign_sku: dict[str, set[str]] = defaultdict(set)
        latest_snapshot_at: datetime | None = None

        for snapshot_at_raw, campaign_id_raw, sku_key_raw in rows:
            parsed = _parse_dt(snapshot_at_raw)
            if parsed is None:
                continue
            if latest_snapshot_at is None or parsed > latest_snapshot_at:
                latest_snapshot_at = parsed
            if parsed < lookback_start:
                continue
            rows_24h += 1
            campaign_id = str(campaign_id_raw).strip()
            sku_key = str(sku_key_raw).strip()
            if campaign_id:
                campaigns_seen.add(campaign_id)
                if sku_key:
                    campaign_sku[campaign_id].add(sku_key)
            if sku_key:
                sku_seen.add(sku_key)

        stale_hours = None
        if latest_snapshot_at is not None:
            stale_hours = max((now_value - latest_snapshot_at).total_seconds() / 3600.0, 0.0)

        missing_expected = sorted(expected_campaigns - campaigns_seen)
        unexpected_campaigns = sorted(campaigns_seen - expected_campaigns) if expected_campaigns else sorted(campaigns_seen)

        status = "ok"
        if rows_24h == 0:
            status = "error"
            failures.append(f"{store_code} ({merchant_id}): no hourly_snapshot rows in last {lookback_hours}h.")
        if stale_hours is None or stale_hours > max_stale_hours:
            status = "error"
            failures.append(f"{store_code} ({merchant_id}): latest snapshot is stale/missing.")
        if missing_expected:
            status = "error"
            failures.append(
                f"{store_code} ({merchant_id}): missing expected campaigns: {', '.join(missing_expected)}."
            )

        acmewear_status, acmewear_note = _build_acmewear_rows_one_note(
            rows_24h=rows_24h,
            expected_campaigns=expected_campaigns,
            missing_expected=missing_expected,
            stale_hours=stale_hours,
            max_stale_hours=max_stale_hours,
        )
        if store_code.upper() == "ACMEWEAR" and acmewear_status == "invalid":
            status = "error"

        stores_report.append(
            {
                "store_code": store_code,
                "merchant_id": merchant_id,
                "status": status,
                "lookback_hours": lookback_hours,
                "rows_24h": rows_24h,
                "campaign_count_24h": len(campaigns_seen),
                "product_count_24h": len(sku_seen),
                "campaign_ids_seen_24h": sorted(campaigns_seen),
                "campaign_product_counts_24h": [
                    {"campaign_id": cid, "products": len(campaign_sku[cid])}
                    for cid in sorted(campaign_sku)
                ],
                "expected_campaign_ids": sorted(expected_campaigns),
                "expected_campaign_source": expected_source,
                "missing_expected_campaign_ids": missing_expected,
                "unexpected_campaign_ids": unexpected_campaigns,
                "latest_snapshot_at": latest_snapshot_at.isoformat() if latest_snapshot_at else None,
                "stale_hours": stale_hours,
                "max_stale_hours": max_stale_hours,
                "acmewear_rows_one_status": acmewear_status if store_code.upper() == "ACMEWEAR" else "n/a",
                "acmewear_rows_one_note": acmewear_note if store_code.upper() == "ACMEWEAR" else "N/A",
            }
        )

    ok = len(failures) == 0
    return {
        "status": "ok" if ok else "error",
        "ok": ok,
        "generated_at": now_value.isoformat(),
        "lookback_hours": lookback_hours,
        "stores": stores_report,
        "failures": failures,
        "exit_code": 0 if ok else 1,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kaspi ads campaign coverage report (campaign/product completeness)."
    )
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH).")
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--merchant-id", default=None, help="Single merchant id override.")
    parser.add_argument("--merchant-ids", default=None, help="Comma-separated merchant ids override.")
    parser.add_argument(
        "--expected-inventory-json",
        type=Path,
        action="append",
        default=[],
        help="Expected campaign inventory JSON path (repeatable).",
    )
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--max-stale-hours", type=float, default=2.0)
    parser.add_argument("--now", default=None, help="Override current local time (ISO-8601).")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to write full JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now_local = _parse_dt(args.now) if args.now else None
    if args.now and now_local is None:
        print(json.dumps({"status": "error", "error": f"Invalid --now value: {args.now!r}"}))
        return 2

    store_targets = _parse_store_targets(args)
    inventory_paths = list(args.expected_inventory_json)
    if not inventory_paths:
        inventory_paths = discover_inventory_json_files()
    expected_campaigns_by_store, inventory_warnings = load_expected_campaigns(inventory_paths)

    ads_db_path = resolve_ads_db_path(
        ads_db_arg=args.ads_db,
        default_path=DEFAULT_WORKTREE_ADS_DB_PATH,
    )
    assert_ads_db_path_safe(ads_db_path=ads_db_path)

    with sqlite3.connect(ads_db_path) as conn:
        report = build_campaign_coverage_report(
            conn,
            store_targets=store_targets,
            expected_campaigns_by_store=expected_campaigns_by_store,
            now_local=now_local,
            lookback_hours=args.lookback_hours,
            max_stale_hours=args.max_stale_hours,
        )
    report["ads_db"] = str(ads_db_path)
    report["inventory_files"] = [str(path) for path in inventory_paths]
    report["inventory_warnings"] = inventory_warnings

    rendered = json.dumps(report, ensure_ascii=False)
    print(rendered)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
