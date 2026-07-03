#!/usr/bin/env python3
"""Build a no-send priority queue for early Kaspi customer size requests.

This script turns the current missing-size candidates plus the local runtime
ledger into an urgency-ranked queue. It is intentionally read-only: it never
opens Kaspi, never sends a message, never writes the ledger, and never writes
Google Board or production DB state.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    OrderCandidate,
    load_missing_size_candidates,
    request_template_hash,
    sha256_file,
    suggest_merchant_status_filter,
)
from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
ACTIONABLE_LEDGER_STATUSES = {"SEND_PLANNED_NO_SEND"}
AFTER_SEND_OR_REPLY_STATUSES = {
    "REQUEST_SENT",
    "REQUEST_SENT_MANUAL_CONFIRMED",
    "POLLING",
    "REPLY_OBSERVED",
    "REPLY_OBSERVED_NO_SIZE_SIGNAL",
    "CLASSIFICATION_READY",
    "SIZE_CONFIRMED",
    "UNKNOWN_SEND_OUTCOME",
    "SEND_IN_PROGRESS",
}
STATUS_PRIORITY_BOOST = {
    "KASPI_DELIVERY_CARGO_ASSEMBLY": 30,
    "KASPI_DELIVERY_WAIT_FOR_COURIER": 20,
    "NEW": 10,
}


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (
        normalized,
        normalized.replace(" ", "T", 1),
        normalized[:19],
        normalized[:10],
    ):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_early_send_priority_{target_date.isoformat()}_{stamp}"
    )


def _safe_file_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _load_ledger_rows_readonly(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    uri = f"file:{ledger_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'customer_size_request_ledger'
            """
        ).fetchone()
        if not table:
            return []
        rows = conn.execute(
            """
            SELECT
                ledger_key, order_ref, db_row_id, store_code, sku_key, sku_id,
                channel, template_hash, status, request_planned_at,
                request_sent_at, last_observed_at, planned_size,
                size_source, size_confidence, send_allowed,
                raw_order_id_exported, raw_reply_text_exported, updated_at
            FROM customer_size_request_ledger
            ORDER BY updated_at DESC, ledger_key
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _latest_ledger_by_order_ref(
    ledger_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        order_ref = str(row.get("order_ref") or "").strip()
        if order_ref and order_ref not in result:
            result[order_ref] = dict(row)
    return result


def _age_minutes(candidate: OrderCandidate, *, as_of: datetime) -> int | None:
    created = _parse_datetime(candidate.created_at)
    if created is None:
        return None
    return max(0, int((as_of - created).total_seconds() // 60))


def _priority_band(
    age_minutes: int | None,
    *,
    high_after_minutes: int,
    critical_after_minutes: int,
) -> str:
    if age_minutes is None:
        return "review_missing_created_at"
    if age_minutes >= critical_after_minutes:
        return f"critical_over_{critical_after_minutes}m"
    if age_minutes >= high_after_minutes:
        return f"high_{high_after_minutes}_{critical_after_minutes}m"
    return f"normal_under_{high_after_minutes}m"


def _priority_score(
    *,
    age_minutes: int | None,
    status_filter: str,
    missing_created_at_penalty: int,
) -> int:
    age_score = age_minutes if age_minutes is not None else missing_created_at_penalty
    return int(age_score) + int(STATUS_PRIORITY_BOOST.get(status_filter, 0))


def _row_for_candidate(
    candidate: OrderCandidate,
    *,
    ledger_row: Mapping[str, Any],
    sequence: int,
    as_of: datetime,
    high_after_minutes: int,
    critical_after_minutes: int,
    missing_created_at_penalty: int,
) -> dict[str, Any]:
    status_filter = suggest_merchant_status_filter(candidate)
    age = _age_minutes(candidate, as_of=as_of)
    expected_merchant_id = merchant_account_id_for_store(candidate.store_code)
    return {
        "sequence": sequence,
        "priority_score": _priority_score(
            age_minutes=age,
            status_filter=status_filter,
            missing_created_at_penalty=missing_created_at_penalty,
        ),
        "priority_band": _priority_band(
            age,
            high_after_minutes=high_after_minutes,
            critical_after_minutes=critical_after_minutes,
        ),
        "age_minutes": age,
        "order_ref": candidate.order_ref,
        "db_row_id": candidate.db_row_id,
        "store_code": candidate.store_code,
        "expected_merchant_account_id": expected_merchant_id,
        "requires_matching_merchant_account": True,
        "suggested_merchant_status_filter": status_filter,
        "internal_status": candidate.internal_status,
        "kaspi_status": candidate.kaspi_status,
        "planned_shipment_date": candidate.planned_shipment_date,
        "created_at": candidate.created_at,
        "sku_key": candidate.sku_key,
        "sku_id": candidate.sku_id,
        "product_type": candidate.product_type,
        "ledger_key": ledger_row.get("ledger_key"),
        "ledger_status": str(ledger_row.get("status") or "").strip().upper(),
        "ledger_request_planned_at": ledger_row.get("request_planned_at"),
        "template_hash": ledger_row.get("template_hash"),
        "suggested_action": "OWNER_APPROVED_LIVE_SEND_CANARY_OR_BATCH_SEND_ONLY",
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }


def build_priority_packet(
    *,
    candidates: list[OrderCandidate],
    ledger_rows: list[dict[str, Any]],
    as_of: datetime,
    high_after_minutes: int,
    critical_after_minutes: int,
    missing_created_at_penalty: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    by_order_ref = _latest_ledger_by_order_ref(ledger_rows)
    blockers: list[str] = []
    excluded: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for candidate in candidates:
        ledger_row = by_order_ref.get(candidate.order_ref)
        if not ledger_row:
            excluded.append(
                {
                    "order_ref": candidate.order_ref,
                    "db_row_id": candidate.db_row_id,
                    "store_code": candidate.store_code,
                    "reason": "missing_local_ledger_row_run_no_send_control_plane_first",
                    "raw_order_id_exported": False,
                }
            )
            blockers.append("current_candidate_missing_local_ledger_row")
            continue
        ledger_status = str(ledger_row.get("status") or "").strip().upper()
        if ledger_status in AFTER_SEND_OR_REPLY_STATUSES:
            excluded.append(
                {
                    "order_ref": candidate.order_ref,
                    "db_row_id": candidate.db_row_id,
                    "store_code": candidate.store_code,
                    "ledger_status": ledger_status,
                    "reason": "already_after_send_or_reply",
                    "raw_order_id_exported": False,
                }
            )
            continue
        if ledger_status not in ACTIONABLE_LEDGER_STATUSES:
            excluded.append(
                {
                    "order_ref": candidate.order_ref,
                    "db_row_id": candidate.db_row_id,
                    "store_code": candidate.store_code,
                    "ledger_status": ledger_status,
                    "reason": "ledger_status_not_actionable_for_send_priority",
                    "raw_order_id_exported": False,
                }
            )
            continue
        if not merchant_account_id_for_store(candidate.store_code):
            blockers.append("missing_expected_merchant_account_id_for_store")
        rows.append(
            _row_for_candidate(
                candidate,
                ledger_row=ledger_row,
                sequence=0,
                as_of=as_of,
                high_after_minutes=high_after_minutes,
                critical_after_minutes=critical_after_minutes,
                missing_created_at_penalty=missing_created_at_penalty,
            )
        )

    rows.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            str(row["store_code"] or ""),
            int(row["db_row_id"] or 0),
            str(row["order_ref"] or ""),
        )
    )
    deduped_rows: list[dict[str, Any]] = []
    seen_order_refs: set[str] = set()
    for row in rows:
        order_ref = str(row.get("order_ref") or "")
        if order_ref in seen_order_refs:
            excluded.append(
                {
                    "order_ref": row.get("order_ref"),
                    "db_row_id": row.get("db_row_id"),
                    "store_code": row.get("store_code"),
                    "ledger_status": row.get("ledger_status"),
                    "reason": "duplicate_current_candidate_same_order_ref_prioritized_once",
                    "raw_order_id_exported": False,
                }
            )
            continue
        seen_order_refs.add(order_ref)
        deduped_rows.append(row)
    rows = deduped_rows
    for index, row in enumerate(rows, start=1):
        row["sequence"] = index
    return rows, excluded, sorted(set(blockers))


def summarize_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    row_list = list(rows)
    by_band = Counter(str(row.get("priority_band") or "UNKNOWN") for row in row_list)
    by_store = Counter(str(row.get("store_code") or "UNKNOWN") for row in row_list)
    by_store_status = Counter(
        (
            str(row.get("store_code") or "UNKNOWN"),
            str(row.get("suggested_merchant_status_filter") or "UNKNOWN"),
        )
        for row in row_list
    )
    return {
        "target_count": len(row_list),
        "by_priority_band": dict(sorted(by_band.items())),
        "by_store": dict(sorted(by_store.items())),
        "by_store_status": [
            {
                "store_code": store,
                "suggested_merchant_status_filter": status,
                "target_count": count,
            }
            for (store, status), count in sorted(by_store_status.items())
        ],
    }


def validate_no_raw_order_id_leak(payload: Mapping[str, Any], candidates: Iterable[OrderCandidate]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    blockers: list[str] = []
    for candidate in candidates:
        raw_order_id = str(candidate.raw_order_id or "").strip()
        if raw_order_id and raw_order_id in text:
            blockers.append("raw_order_id_value_detected")
            break
    return blockers


def _render_closeout(manifest: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Size Early Send Priority Packet",
            "",
            f"Gate: {manifest['gate']}",
            "",
            f"- Output folder: `{manifest['output_dir']}`",
            f"- Target date: `{manifest['target_date']}`",
            f"- Current missing-size candidates: `{manifest['candidate_count']}`",
            f"- Priority targets: `{manifest['priority_target_count']}`",
            f"- Excluded current candidates: `{manifest['excluded_candidate_count']}`",
            f"- Blockers: `{manifest['blockers_count']}`",
            f"- App DB unchanged: `{str(manifest['app_db_unchanged']).lower()}`",
            f"- Local ledger unchanged: `{str(manifest['ledger_db_unchanged']).lower()}`",
            "",
            "No Kaspi browser action, customer message, Google Board write, production DB",
            "write, Telegram send, workbook change, scheduler change, or external write was",
            "performed. This packet is a no-send prioritization surface only.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build redacted early-send priority evidence for Kaspi customer size requests."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[], help="Optional store_code filter.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--template", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument("--as-of", help="ISO timestamp. Defaults to current local time.")
    parser.add_argument("--high-after-minutes", type=int, default=60)
    parser.add_argument("--critical-after-minutes", type=int, default=120)
    parser.add_argument("--missing-created-at-penalty", type=int, default=30)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    as_of = _parse_datetime(args.as_of) if args.as_of else datetime.now()
    if as_of is None:
        raise SystemExit("--as-of must be an ISO timestamp")
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    app_db_sha_before = _safe_file_sha(db_path)
    ledger_db_sha_before = _safe_file_sha(ledger_path)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=args.store,
        limit=args.limit,
    )
    ledger_rows = _load_ledger_rows_readonly(ledger_path)
    priority_rows, excluded_rows, blockers = build_priority_packet(
        candidates=candidates,
        ledger_rows=ledger_rows,
        as_of=as_of,
        high_after_minutes=args.high_after_minutes,
        critical_after_minutes=args.critical_after_minutes,
        missing_created_at_penalty=args.missing_created_at_penalty,
    )

    redaction_blockers = validate_no_raw_order_id_leak(
        {
            "priority_rows": priority_rows,
            "excluded_rows": excluded_rows,
            "ledger_rows": ledger_rows,
        },
        candidates,
    )
    blockers = sorted(set([*blockers, *redaction_blockers]))

    if redaction_blockers:
        gate = "RED_EARLY_SEND_PRIORITY_PACKET_RAW_ORDER_LEAK_STOP_NO_WRITE"
    elif blockers:
        gate = "YELLOW_EARLY_SEND_PRIORITY_PACKET_BLOCKED_NO_WRITE"
    elif not priority_rows:
        gate = "YELLOW_EARLY_SEND_PRIORITY_PACKET_NO_PENDING_TARGETS_NO_WRITE"
    else:
        gate = "GREEN_EARLY_SEND_PRIORITY_PACKET_READY_NO_WRITE"

    app_db_sha_after = _safe_file_sha(db_path)
    ledger_db_sha_after = _safe_file_sha(ledger_path)
    summary = summarize_rows(priority_rows)
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "app_db_path": str(db_path),
        "app_db_sha256_before": app_db_sha_before,
        "app_db_sha256_after": app_db_sha_after,
        "app_db_unchanged": app_db_sha_before == app_db_sha_after,
        "ledger_db_path": str(ledger_path),
        "ledger_db_exists": ledger_path.exists(),
        "ledger_db_sha256_before": ledger_db_sha_before,
        "ledger_db_sha256_after": ledger_db_sha_after,
        "ledger_db_unchanged": ledger_db_sha_before == ledger_db_sha_after,
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "stores": args.store,
        "candidate_count": len(candidates),
        "ledger_row_count": len(ledger_rows),
        "priority_target_count": len(priority_rows),
        "excluded_candidate_count": len(excluded_rows),
        "priority_summary": summary,
        "sla_config": {
            "high_after_minutes": args.high_after_minutes,
            "critical_after_minutes": args.critical_after_minutes,
            "missing_created_at_penalty": args.missing_created_at_penalty,
        },
        "template_hash": request_template_hash(args.template),
        "template_text_not_exported": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_ids_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "requires_matching_merchant_account": True,
        "blockers": blockers,
        "blockers_count": len(blockers),
    }

    _write_json(output_dir / "priority_targets_redacted.json", priority_rows)
    _write_csv(output_dir / "priority_targets_redacted.csv", priority_rows)
    _write_json(output_dir / "excluded_current_candidates_redacted.json", excluded_rows)
    _write_csv(output_dir / "excluded_current_candidates_redacted.csv", excluded_rows)
    _write_json(output_dir / "priority_summary.json", summary)
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_render_closeout(manifest), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate.startswith(("GREEN_", "YELLOW_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
