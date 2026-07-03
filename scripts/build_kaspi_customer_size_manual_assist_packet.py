#!/usr/bin/env python3
"""Build a local manual-assist queue for Kaspi customer size requests.

This helper is the safe fallback after the Kaspi chat open/send automation lane
failed RED. It never opens Kaspi, never sends or types a message, never writes
Google Board, and never mutates the production app DB. It only packages a
redacted operator queue plus exact local recorder commands for manual outcomes.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from core.ops.customer_size_request import DEFAULT_REQUEST_TEMPLATE, request_template_hash, sha256_file
from scripts.build_kaspi_customer_size_early_send_priority_packet import (
    DEFAULT_DB,
    DEFAULT_LEDGER_DB,
    _default_output_dir as _priority_default_output_dir,
    _load_ledger_rows_readonly,
    _parse_date,
    _parse_datetime,
    _safe_file_sha,
    _write_csv,
    _write_json,
    build_priority_packet,
    load_missing_size_candidates,
    summarize_rows,
    validate_no_raw_order_id_leak,
)


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        Path(__file__).resolve().parents[1]
        / "exports"
        / "validation"
        / f"kaspi_customer_size_manual_assist_{target_date.isoformat()}_{stamp}"
    )


def _manual_command(row: Mapping[str, Any], *, ledger_path: Path) -> str:
    return " ".join(
        [
            "PYTHONPATH=. .venv/bin/python",
            "scripts/record_kaspi_customer_size_manual_action_outcome.py",
            f"--ledger-db {ledger_path}",
            f"--order-ref {row.get('order_ref')}",
            f"--template-hash {row.get('template_hash')}",
            "--outcome sent_manual",
            "--operator-confirmed-manual-action",
            "--confirm-no-auto-type",
            "--confirm-no-raw-export",
        ]
    )


def _manual_row(row: Mapping[str, Any], *, ledger_path: Path) -> dict[str, Any]:
    result = dict(row)
    result["suggested_action"] = "OWNER_MANUAL_KASPI_SIZE_REQUEST"
    result["manual_action_channel"] = "KASPI_MERCHANT_CHAT_MANUAL_OWNER"
    result["manual_outcome_command"] = _manual_command(row, ledger_path=ledger_path)
    result["automation_must_not_open_chat"] = True
    result["automation_must_not_type_or_send"] = True
    return result


def _render_queue_md(*, manifest: Mapping[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Kaspi Customer Size Manual-Assist Queue",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "This queue is for owner/operator manual action only. Automation must not open chat, type, send, replay endpoints, or export raw customer/session data.",
        "",
        f"- Target date: `{manifest['target_date']}`",
        f"- Queue rows: `{manifest['manual_assist_target_count']}`",
        f"- Template hash: `{manifest['template_hash']}`",
        f"- App DB unchanged: `{str(manifest['app_db_unchanged']).lower()}`",
        f"- Ledger unchanged: `{str(manifest['ledger_db_unchanged']).lower()}`",
        "",
        "## Rows",
        "",
    ]
    if not rows:
        lines.append("No manual-assist rows are currently actionable.")
    for row in rows:
        lines.extend(
            [
                f"### {row.get('sequence')}. {row.get('store_code')} / merchant `{row.get('expected_merchant_account_id')}`",
                "",
                f"- Priority: `{row.get('priority_band')}` / score `{row.get('priority_score')}`",
                f"- Redacted order ref: `{row.get('order_ref')}`",
                f"- DB row: `{row.get('db_row_id')}`",
                f"- Status filter: `{row.get('suggested_merchant_status_filter')}`",
                f"- SKU: `{row.get('sku_key')}` / `{row.get('sku_id')}`",
                f"- Manual outcome command after owner sends: `{row.get('manual_outcome_command')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety",
            "",
            "- Customer send performed by automation: false",
            "- Kaspi chat write performed by automation: false",
            "- Browser action performed by this helper: false",
            "- Raw order/customer/session export: false",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[])
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
    output_dir = (args.output_dir or _default_output_dir(target_date)).resolve()
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
    manual_rows = [_manual_row(row, ledger_path=ledger_path) for row in priority_rows]
    redaction_blockers = validate_no_raw_order_id_leak(
        {"manual_rows": manual_rows, "excluded_rows": excluded_rows},
        candidates,
    )
    blockers = sorted(set([*blockers, *redaction_blockers]))
    if redaction_blockers:
        gate = "RED_MANUAL_ASSIST_QUEUE_RAW_ORDER_LEAK_STOP_NO_LIVE_ACTION"
    elif blockers:
        gate = "YELLOW_MANUAL_ASSIST_QUEUE_BLOCKED_NO_LIVE_ACTION"
    elif not manual_rows:
        gate = "YELLOW_MANUAL_ASSIST_QUEUE_NO_ACTIONABLE_ROWS_NO_LIVE_ACTION"
    else:
        gate = "GREEN_MANUAL_ASSIST_QUEUE_READY_NO_LIVE_ACTION"

    app_db_sha_after = _safe_file_sha(db_path)
    ledger_db_sha_after = _safe_file_sha(ledger_path)
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "priority_packet_output_hint": str(_priority_default_output_dir(target_date)),
        "app_db_path": str(db_path),
        "app_db_sha256_before": app_db_sha_before,
        "app_db_sha256_after": app_db_sha_after,
        "app_db_unchanged": app_db_sha_before == app_db_sha_after,
        "ledger_db_path": str(ledger_path),
        "ledger_db_sha256_before": ledger_db_sha_before,
        "ledger_db_sha256_after": ledger_db_sha_after,
        "ledger_db_unchanged": ledger_db_sha_before == ledger_db_sha_after,
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "manual_assist_target_count": len(manual_rows),
        "excluded_candidate_count": len(excluded_rows),
        "manual_assist_summary": summarize_rows(manual_rows),
        "template_hash": request_template_hash(args.template),
        "template_text_not_exported": True,
        "customer_send_performed_by_automation": False,
        "kaspi_chat_write_performed_by_automation": False,
        "browser_action_performed": False,
        "endpoint_replay_performed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_ids_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": blockers,
        "blockers_count": len(blockers),
    }
    _write_json(output_dir / "manual_assist_targets_redacted.json", manual_rows)
    _write_csv(output_dir / "manual_assist_targets_redacted.csv", manual_rows)
    _write_json(output_dir / "excluded_current_candidates_redacted.json", excluded_rows)
    _write_json(output_dir / "manual_assist_summary.json", manifest["manual_assist_summary"])
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "manual_assist_queue.md").write_text(
        _render_queue_md(manifest=manifest, rows=manual_rows),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate.startswith(("GREEN_", "YELLOW_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
