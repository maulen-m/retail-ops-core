#!/usr/bin/env python3
"""Materialize provenance-only Meta external ads spend rows.

Default: dry run. Apply requires ENABLE_META_EXTERNAL_ADS_SPEND_WRITE=1 and
--apply. This script records source spend provenance only; it does not assign
spend to SKUs, orders, products, profit, or publication attribution.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH


ENV_GATE = "ENABLE_META_EXTERNAL_ADS_SPEND_WRITE"
TABLE_NAME = "meta_external_ads_spend_daily"
SOURCE_SYSTEM = "meta_instagram"


class MetaExternalAdsSpendError(RuntimeError):
    """Raised when Meta external spend ingestion cannot proceed."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _load_packet(packet_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MetaExternalAdsSpendError(f"packet JSON parse failed: {packet_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetaExternalAdsSpendError("packet root must be a JSON object")
    return payload


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MetaExternalAdsSpendError(f"{label} JSON parse failed: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetaExternalAdsSpendError(f"{label} root must be a JSON object: {path}")
    return payload


def _date_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise MetaExternalAdsSpendError(f"{field} must be a list")
    out: list[str] = []
    for item in value:
        text = str(item or "")[:10]
        try:
            datetime.fromisoformat(text)
        except ValueError as exc:
            raise MetaExternalAdsSpendError(f"{field} contains invalid date: {item}") from exc
        out.append(text)
    return out


def _date_results_by_date(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = packet.get("date_results")
    if not isinstance(value, list):
        raise MetaExternalAdsSpendError("date_results must be a list")
    out: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise MetaExternalAdsSpendError("date_results entries must be objects")
        date = str(item.get("date") or "")[:10]
        if not date:
            raise MetaExternalAdsSpendError("date_results entry missing date")
        out[date] = item
    return out


def _raw_evidence_path(packet: dict[str, Any], date: str, result: dict[str, Any]) -> Path:
    raw_paths = packet.get("raw_evidence_paths")
    path_text: str | None = None
    if isinstance(raw_paths, dict) and raw_paths.get(date):
        path_text = str(raw_paths[date])
    elif result.get("raw_evidence_path"):
        path_text = str(result["raw_evidence_path"])
    if not path_text:
        raise MetaExternalAdsSpendError(f"raw evidence path missing for {date}")
    path = Path(path_text).expanduser()
    if not path.exists() or not path.is_file():
        raise MetaExternalAdsSpendError(f"raw evidence file missing for {date}: {path}")
    return path


def _spend_by_date(packet: dict[str, Any], requested_dates: list[str]) -> dict[str, float]:
    results = _date_results_by_date(packet)
    packet_spend = packet.get("spend_by_date")
    out: dict[str, float] = {}
    for date in requested_dates:
        amount = None
        if isinstance(packet_spend, dict):
            amount = _to_float(packet_spend.get(date))
        result_amount = _to_float((results.get(date) or {}).get("spend"))
        amount = max(_to_float(amount), result_amount)
        if amount > 0:
            out[date] = amount
    return out


def _count_rows_by_level(packet: dict[str, Any], date: str) -> dict[str, int]:
    result = (_date_results_by_date(packet).get(date) or {})
    counts = result.get("row_counts_by_level")
    if isinstance(counts, dict):
        return {
            "campaign": _to_int(counts.get("campaign")),
            "adset": _to_int(counts.get("adset")),
            "ad": _to_int(counts.get("ad")),
        }
    by_date = packet.get("row_counts_by_date_and_level")
    if isinstance(by_date, dict) and isinstance(by_date.get(date), dict):
        date_counts = by_date[date]
        return {
            "campaign": _to_int(date_counts.get("campaign")),
            "adset": _to_int(date_counts.get("adset")),
            "ad": _to_int(date_counts.get("ad")),
        }
    return {"campaign": 0, "adset": 0, "ad": 0}


def _validate_packet(packet: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in [
        "platform_writes_occurred",
        "budget_status_campaign_adset_ad_writes_occurred",
        "autonomous_business_writes_performed",
        "deterministic_purchase_attribution_claimed",
    ]:
        if packet.get(field) is not False:
            issues.append(f"{field}_must_be_false")
    if packet.get("any_spend_found") is not True:
        issues.append("any_spend_found_must_be_true")
    return issues


def _build_rows(
    *,
    packet_path: Path,
    store_code: str,
    source_system: str,
    run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packet = _load_packet(packet_path)
    issues = _validate_packet(packet)
    requested_dates = _date_list(packet.get("dates_requested"), field="dates_requested")
    fetched_dates = _date_list(
        packet.get("dates_successfully_fetched"), field="dates_successfully_fetched"
    )
    if set(requested_dates) != set(fetched_dates):
        issues.append("requested_dates_not_all_fetched")
    results = _date_results_by_date(packet)
    positive_spend = _spend_by_date(packet, requested_dates)
    if not positive_spend:
        issues.append("positive_spend_missing")

    packet_sha = _sha256(packet_path)
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    packet_account_id = str(packet.get("account_id") or "").strip()
    account_ids: set[str] = set()
    for date, spend_amount in sorted(positive_spend.items()):
        result = results.get(date) or {}
        if result.get("source_status") != "SUCCESS":
            issues.append(f"source_status_not_success:{date}")
        if result.get("clears_source_freshness") is not True:
            issues.append(f"does_not_clear_source_freshness:{date}")
        raw_path = _raw_evidence_path(packet, date, result)
        raw_evidence = _load_json_object(raw_path, label=f"raw evidence for {date}")
        raw_account_id = str(raw_evidence.get("account_id") or "").strip()
        account_id = packet_account_id or raw_account_id
        if not account_id:
            issues.append(f"account_id_missing:{date}")
        else:
            account_ids.add(account_id)
        counts = _count_rows_by_level(packet, date)
        rows.append(
            {
                "date": date,
                "store_code": store_code.upper(),
                "source_system": source_system,
                "account_id": account_id,
                "spend_amount": spend_amount,
                "currency_code": str(packet.get("account_currency") or "UNKNOWN_META_ACCOUNT_CURRENCY"),
                "spend_basis": str(result.get("spend_basis") or "campaign"),
                "campaign_row_count": counts["campaign"],
                "adset_row_count": counts["adset"],
                "ad_row_count": counts["ad"],
                "packet_path": str(packet_path),
                "packet_sha256": packet_sha,
                "raw_evidence_path": str(raw_path),
                "raw_evidence_sha256": _sha256(raw_path),
                "raw_source_run_id": str(packet.get("raw_source_run_id") or packet.get("run_id") or ""),
                "raw_source_fetched_at": str(packet.get("raw_source_fetched_at") or packet.get("fetched_at") or ""),
                "generated_at_utc": str(packet.get("generated_at_utc") or ""),
                "publication_attribution_claimed": 0,
                "run_id": run_id,
                "ingested_at": now,
                "created_by": "materialize_meta_external_ads_spend",
            }
        )

    summary = {
        "packet_path": str(packet_path),
        "packet_sha256": packet_sha,
        "store_code": store_code.upper(),
        "source_system": source_system,
        "requested_dates": requested_dates,
        "positive_spend_dates": sorted(positive_spend),
        "account_ids": sorted(account_ids),
        "issues": issues,
        "candidate_rows": len(rows),
        "candidate_spend_amount": round(sum(row["spend_amount"] for row in rows), 6),
    }
    if issues:
        raise MetaExternalAdsSpendError(json.dumps(summary, ensure_ascii=False, indent=2))
    return rows, summary


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            source_system TEXT NOT NULL,
            account_id TEXT NOT NULL,
            spend_amount REAL NOT NULL,
            currency_code TEXT NOT NULL,
            spend_basis TEXT NOT NULL,
            campaign_row_count INTEGER NOT NULL DEFAULT 0,
            adset_row_count INTEGER NOT NULL DEFAULT 0,
            ad_row_count INTEGER NOT NULL DEFAULT 0,
            packet_path TEXT NOT NULL,
            packet_sha256 TEXT NOT NULL,
            raw_evidence_path TEXT NOT NULL,
            raw_evidence_sha256 TEXT NOT NULL,
            raw_source_run_id TEXT,
            raw_source_fetched_at TEXT,
            generated_at_utc TEXT,
            publication_attribution_claimed INTEGER NOT NULL DEFAULT 0,
            run_id TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            PRIMARY KEY (source_system, store_code, date, account_id)
        )
        """
    )


def materialize_meta_external_ads_spend(
    *,
    db_path: Path,
    packet_path: Path,
    store_code: str,
    source_system: str = SOURCE_SYSTEM,
    run_id: str,
    output_root: Path,
    apply: bool,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    rows, summary = _build_rows(
        packet_path=packet_path.expanduser().resolve(),
        store_code=store_code,
        source_system=source_system,
        run_id=run_id,
    )
    before_count = 0
    after_count = 0
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise MetaExternalAdsSpendError(f"{ENV_GATE}=1 is required with --apply")
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            before_row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (TABLE_NAME,),
            ).fetchone()
            had_table = bool(before_row and int(before_row[0]) > 0)
            if had_table:
                before_count = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
            _ensure_table(conn)
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {TABLE_NAME} (
                    date, store_code, source_system, account_id, spend_amount,
                    currency_code, spend_basis, campaign_row_count, adset_row_count,
                    ad_row_count, packet_path, packet_sha256, raw_evidence_path,
                    raw_evidence_sha256, raw_source_run_id, raw_source_fetched_at,
                    generated_at_utc, publication_attribution_claimed, run_id,
                    ingested_at, created_by
                ) VALUES (
                    :date, :store_code, :source_system, :account_id, :spend_amount,
                    :currency_code, :spend_basis, :campaign_row_count,
                    :adset_row_count, :ad_row_count, :packet_path, :packet_sha256,
                    :raw_evidence_path, :raw_evidence_sha256, :raw_source_run_id,
                    :raw_source_fetched_at, :generated_at_utc,
                    :publication_attribution_claimed, :run_id, :ingested_at,
                    :created_by
                )
                """,
                rows,
            )
            after_count = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
            conn.commit()
    report = {
        **summary,
        "db_path": str(db_path),
        "apply": apply,
        "table": TABLE_NAME,
        "rows": rows,
        "table_count_before": before_count,
        "table_count_after": after_count,
    }
    report_path = output_root / "meta_external_ads_spend_materialization_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Meta external ads spend provenance")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--store-code", default="ACMEWEAR")
    parser.add_argument("--source-system", default=SOURCE_SYSTEM)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        report = materialize_meta_external_ads_spend(
            db_path=args.db,
            packet_path=args.packet,
            store_code=args.store_code,
            source_system=args.source_system,
            run_id=args.run_id,
            output_root=args.output_root,
            apply=args.apply,
        )
    except (MetaExternalAdsSpendError, FileNotFoundError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"status=PASS")
    print(f"applied={report['apply']}")
    print(f"candidate_rows={report['candidate_rows']}")
    print(f"candidate_spend_amount={report['candidate_spend_amount']}")
    print(f"table_count_before={report['table_count_before']}")
    print(f"table_count_after={report['table_count_after']}")
    print(f"report_path={report['report_path']}")
    if not args.apply:
        print("DRY RUN: no DB writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
