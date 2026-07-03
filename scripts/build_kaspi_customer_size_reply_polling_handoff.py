#!/usr/bin/env python3
"""Build a redacted handoff for polling Kaspi customer-size replies.

This script does not open Kaspi, read customer chats, send messages, write
Google Board, or copy raw customer reply text. It packages the next UI-helper
steps for rows that already have a recorded size-request send.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    export_customer_size_ledger_snapshot,
    sha256_file,
    summarize_customer_size_ledger,
)
from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
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
POLLABLE_STATUSES = {"REQUEST_SENT", "REQUEST_SENT_MANUAL_CONFIRMED", "POLLING"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_reply_polling_handoff_{stamp}"


def _poll_targets(ledger_rows: list[dict[str, Any]], *, limit: int | None) -> list[dict[str, Any]]:
    rows = [
        row
        for row in ledger_rows
        if str(row.get("status") or "").strip().upper() in POLLABLE_STATUSES
    ]
    rows.sort(
        key=lambda row: (
            str(row.get("request_sent_at") or row.get("updated_at") or ""),
            str(row.get("store_code") or ""),
            str(row.get("order_ref") or ""),
        )
    )
    if limit is not None:
        rows = rows[: max(0, limit)]
    targets: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        targets.append(
            {
                "sequence": index,
                "ledger_key": row.get("ledger_key"),
                "order_ref": row.get("order_ref"),
                "db_row_id": row.get("db_row_id"),
                "store_code": row.get("store_code"),
                "requires_matching_merchant_account": True,
                "expected_merchant_account_id": merchant_account_id_for_store(row.get("store_code")),
                "sku_key": row.get("sku_key"),
                "sku_id": row.get("sku_id"),
                "status": row.get("status"),
                "request_sent_at": row.get("request_sent_at"),
                "last_observed_at": row.get("last_observed_at"),
                "suggested_action": "READ_CUSTOMER_REPLY_NO_SEND_THEN_TRANSIENT_CSV",
                "raw_order_id_exported": False,
                "raw_reply_text_exported": False,
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "google_board_write_allowed": False,
                "db_write_allowed": False,
            }
        )
    return targets


def _build_handoff(*, output_dir: Path, db_path: Path, ledger_path: Path, targets: list[dict[str, Any]]) -> str:
    first = targets[0] if targets else {}
    resolver_example = ""
    if first:
        resolver_example = "\n".join(
            [
                "```bash",
                "cd ~/Docs/Autonomous_business",
                "RAW_ORDER_ID=\"$(",
                "  PYTHONPATH=. .venv/bin/python scripts/resolve_kaspi_customer_size_order_runtime_secret.py \\",
                f"    --db {db_path} \\",
                f"    --db-row-id {first.get('db_row_id')} \\",
                f"    --order-ref {first.get('order_ref')} \\",
                f"    --audit-json {output_dir}/runtime_secret_audits/target_001_audit_redacted.json \\",
                "    --print-raw-order-id",
                ")\"",
                "printf '%s' \"$RAW_ORDER_ID\" | pbcopy",
                "unset RAW_ORDER_ID",
                "```",
            ]
        )
    return "\n".join(
        [
            "# Kaspi Customer Size Reply Polling Handoff",
            "",
            "Gate: GREEN_REPLY_POLLING_HANDOFF_READY_NO_EXTERNAL_WRITE" if targets else "Gate: YELLOW_REPLY_POLLING_HANDOFF_NO_POLLABLE_ROWS_NO_EXTERNAL_WRITE",
            "",
            "## Mission",
            "",
            "Use a UI-capable helper runtime to read replies for already-sent customer-size requests, then feed only transient raw reply text into the local parser. Do not send or type any customer messages.",
            "",
            "## Evidence",
            "",
            f"- Output dir: `{output_dir}`",
            f"- Ledger DB: `{ledger_path}`",
            f"- Poll targets: `{output_dir / 'reply_poll_targets_redacted.json'}`",
            f"- Transient CSV template: `{output_dir / 'TRANSIENT_REPLY_CSV_TEMPLATE_NO_CUSTOMER_TEXT.csv'}`",
            "",
            "## Runtime Raw Order Resolution",
            "",
            "Resolve raw order IDs only at browser action time. Use them only in the Kaspi merchant order search field. Do not write raw order IDs to Markdown, JSON, screenshots, chat, terminal logs, or closeouts.",
            "",
            resolver_example or "No pollable target exists yet.",
            "",
            "Repeat the resolver command per target using the redacted target file. Each audit JSON must stay redacted.",
            "",
            "## Allowed UI Actions",
            "",
            "- For each target, select/confirm the Kaspi merchant account dropdown matches that target's `expected_merchant_account_id` before searching or opening chat.",
            "- Search the runtime-only raw order ID.",
            "- Open the existing customer chat for that exact order.",
            "- Read customer replies after the request was sent.",
            "- Copy only the minimal reply content into a local transient CSV under `/tmp`.",
            "",
            "## Forbidden Actions",
            "",
            "- No customer message typing or sending.",
            "- No raw order ID/customer reply text/phone/address/cookie/token/session export.",
            "- No Google Board, production DB, CRM workbook, Telegram, WhatsApp, scheduler, or workbook write.",
            "",
            "## Transient Reply CSV",
            "",
            "Copy the template to `/tmp/kaspi_size_replies.csv`, fill only rows that actually have a customer reply, and keep that file out of evidence:",
            "",
            "```csv",
            "db_row_id,order_ref,reply_text,product_type",
            "```",
            "",
            "## Record Reply Facts",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "PYTHONPATH=. .venv/bin/python scripts/record_kaspi_customer_size_reply_observations.py \\",
            f"  --ledger-db {ledger_path} \\",
            "  --reply-csv /tmp/kaspi_size_replies.csv \\",
            f"  --output-dir {output_dir}/reply_observations_after_poll",
            "```",
            "",
            "## Build Google Board Patch Packet",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "PYTHONPATH=. .venv/bin/python scripts/build_kaspi_customer_size_google_board_patch_packet.py \\",
            f"  --db {db_path} \\",
            f"  --ledger-db {ledger_path} \\",
            f"  --output-dir {output_dir}/google_board_patch_after_poll",
            "```",
            "",
            "Stop after local evidence. Do not apply Google Board writes without a separate exact owner approval.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)
    ledger_rows = export_customer_size_ledger_snapshot(ledger_path)
    summary = summarize_customer_size_ledger(ledger_rows)
    targets = _poll_targets(ledger_rows, limit=args.limit)

    _write_json(output_dir / "reply_poll_targets_redacted.json", targets)
    _write_csv(output_dir / "reply_poll_targets_redacted.csv", targets)
    _write_csv(
        output_dir / "TRANSIENT_REPLY_CSV_TEMPLATE_NO_CUSTOMER_TEXT.csv",
        [
            {
                "db_row_id": row.get("db_row_id"),
                "order_ref": row.get("order_ref"),
                "reply_text": "",
                "product_type": "CL",
            }
            for row in targets
        ],
    )
    handoff_path = output_dir / "KASPI_CUSTOMER_SIZE_REPLY_POLLING_HANDOFF.md"
    starter_path = output_dir / "ONE_SENTENCE_STARTER_PROMPT.txt"
    _write_text(
        handoff_path,
        _build_handoff(output_dir=output_dir, db_path=db_path, ledger_path=ledger_path, targets=targets),
    )
    _write_text(
        starter_path,
        (
            f"Read {handoff_path}, poll only the redacted already-sent Kaspi customer-size "
            "targets for replies without sending anything, record reply facts through the provided "
            "transient CSV command, build the Google Board patch packet, and stop."
        )
        + "\n",
    )

    gate = (
        "GREEN_REPLY_POLLING_HANDOFF_READY_NO_EXTERNAL_WRITE"
        if targets
        else "YELLOW_REPLY_POLLING_HANDOFF_NO_POLLABLE_ROWS_NO_EXTERNAL_WRITE"
    )
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": _safe_sha(db_path),
        "db_unchanged": db_sha_before == _safe_sha(db_path),
        "ledger_db_path": str(ledger_path),
        "ledger_sha256_before": ledger_sha_before,
        "ledger_sha256_after": _safe_sha(ledger_path),
        "ledger_unchanged": ledger_sha_before == _safe_sha(ledger_path),
        "ledger_summary": summary,
        "poll_target_count": len(targets),
        "handoff_path": str(handoff_path),
        "starter_prompt_path": str(starter_path),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Reply Polling Handoff",
                "",
                f"Gate: {gate}",
                "",
                f"- Poll targets: {len(targets)}",
                f"- Handoff: {handoff_path}",
                f"- Starter prompt: {starter_path}",
                "- Customer send allowed: false",
                "- Raw order ID exported: false",
                "- Raw reply text exported: false",
                "",
                "No customer messages, Kaspi UI/API writes, Google Board writes, production DB writes,",
                "Telegram sends, scheduler changes, or external writes happened.",
                "",
            ]
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
