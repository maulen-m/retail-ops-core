#!/usr/bin/env python3
"""Build an owner-approval handoff for applying customer-size rows to Google Board.

This script does not write Google Board. It consumes the no-write patch packet
and produces an exact approval phrase plus a guarded execution runbook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
GREEN_PATCH_GATE = "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_google_board_apply_handoff_{stamp}"


def _latest_patch_manifest() -> Path | None:
    matches = [
        path
        for path in REPO_ROOT.glob(
            "exports/validation/kaspi_customer_size_google_board_patch_packet_*/manifest.json"
        )
        if path.is_file()
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _redacted_rows(patch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in patch_rows:
        rows.append(
            {
                "target_tab": row.get("target_tab"),
                "key_column": row.get("key_column"),
                "key_value": row.get("key_value"),
                "source_column": row.get("source_column"),
                "planned_cell_value": row.get("planned_cell_value"),
                "order_ref": row.get("order_ref"),
                "store_code": row.get("store_code"),
                "sku_key": row.get("sku_key"),
                "sku_id": row.get("sku_id"),
                "size_source": row.get("size_source"),
                "size_confidence": row.get("size_confidence"),
                "raw_order_id_exported": False,
                "raw_reply_text_exported": False,
            }
        )
    return rows


def _approval_phrase(
    *,
    patch_manifest_path: Path,
    patch_manifest_sha: str,
    patch_rows_path: Path,
    patch_rows_sha: str,
    patch_rows_count: int,
    target_tab: str,
    source_column: str,
) -> str:
    return (
        "I approve KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_PATCH_APPLY: apply exactly "
        f"{patch_rows_count} customer-size patch row(s) to Google Ops Board tab {target_tab}, "
        f"editing only column {source_column} and only rows identified by _db_row_id in the "
        f"approved patch packet {patch_rows_path} / sha256={patch_rows_sha}. Patch manifest: "
        f"{patch_manifest_path} / sha256={patch_manifest_sha}. After the board patch, run the "
        "existing dry-run/readback size-writeback and workflow readiness commands only. No Kaspi "
        "chat/customer messages, no Telegram/WhatsApp sends, no production DB apply, no shipping, "
        "no waybill build/send, no scheduler changes, no workbook writes, no price/stock/cash/"
        "supplier/PO action, and no unrelated Google Board edits are approved."
    )


def _build_handoff(
    *,
    output_dir: Path,
    patch_manifest_path: Path,
    patch_rows_path: Path,
    patch_rows: list[dict[str, Any]],
    approval_phrase: str,
) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Size Google Board MY_SIZE Apply Handoff",
            "",
            "Gate: GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE",
            "",
            "## Mission",
            "",
            "After the human owner pastes the exact approval phrase, apply the prepared customer-size values to Google Ops Board `SalesRaw_Today.MY_SIZE` only, then run readback/dry-run follow-up gates. This handoff itself performs no write.",
            "",
            "## Required Exact Owner Approval",
            "",
            "```text",
            approval_phrase,
            "```",
            "",
            "## Source Evidence",
            "",
            f"- Patch manifest: `{patch_manifest_path}`",
            f"- Patch rows: `{patch_rows_path}`",
            f"- Redacted apply rows: `{output_dir / 'google_board_my_size_apply_rows_redacted.json'}`",
            "",
            "## Apply Scope",
            "",
            "- Edit only `SalesRaw_Today.MY_SIZE`.",
            "- Match rows only by `_db_row_id` from the patch rows.",
            "- Do not edit system-owned columns, Run_Control, Orders_Today, workbook, DB, Kaspi, Telegram, or scheduler state.",
            "- Stop if any target row is missing, has a nonblank conflicting `MY_SIZE`, or the board layout contract is not current.",
            "",
            "## Current Implementation Boundary",
            "",
            "The execution agent may use the existing Google Ops Board client and `update_tab_rows` pattern to write the cells after exact approval. If a dedicated apply script is not yet present in that runtime, implement the narrow writer first with default no-write behavior and require `--apply` plus `ENABLE_GOOGLE_OPS_BOARD_WRITE=1` before any board mutation.",
            "",
            "## Post-Apply Readback",
            "",
            "After the board patch lands, run the existing size writeback dry-run to confirm DB updates that would be produced:",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "PYTHONPATH=. .venv/bin/python scripts/sync_google_ops_board_sizes_to_db.py \\",
            "  --target-date today \\",
            "  --lookback-days 5 \\",
            f"  --output-json {output_dir}/post_board_patch_size_writeback_dry_run.json",
            "```",
            "",
            "Then rebuild workflow readiness using the latest reply observation, patch, and cadence manifests. Do not run production DB apply or waybill/Telegram closeout without a later exact owner approval.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-manifest", type=Path)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    patch_manifest_path = (args.patch_manifest or _latest_patch_manifest())
    if patch_manifest_path is None:
        manifest = {
            "gate": "YELLOW_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_BLOCKED_NO_PATCH_MANIFEST",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "blockers": ["patch_manifest_missing"],
            "approval_phrase_generated": False,
            "google_board_write_allowed_now": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", f"# Google Board MY_SIZE Apply Handoff\n\nGate: {manifest['gate']}\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    patch_manifest_path = patch_manifest_path.resolve()
    patch_manifest = _read_json(patch_manifest_path)
    patch_rows_path = patch_manifest_path.parent / "google_board_my_size_patch_rows_no_write.json"
    blockers: list[str] = []
    if patch_manifest.get("gate") != GREEN_PATCH_GATE:
        blockers.append("patch_manifest_not_green")
    if not patch_rows_path.is_file():
        blockers.append("patch_rows_missing")
    patch_rows = _read_json(patch_rows_path) if patch_rows_path.is_file() else []
    if not isinstance(patch_rows, list):
        blockers.append("patch_rows_not_list")
        patch_rows = []
    if int(patch_manifest.get("patch_rows_count") or 0) != len(patch_rows):
        blockers.append("patch_rows_count_mismatch")
    if not patch_rows:
        blockers.append("patch_rows_empty")

    if blockers:
        manifest = {
            "gate": "YELLOW_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_BLOCKED_PATCH_NOT_READY",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "patch_manifest_path": str(patch_manifest_path),
            "patch_manifest_gate": patch_manifest.get("gate"),
            "blockers": blockers,
            "approval_phrase_generated": False,
            "google_board_write_allowed_now": False,
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
                    "# Kaspi Customer Size Google Board MY_SIZE Apply Handoff",
                    "",
                    f"Gate: {manifest['gate']}",
                    "",
                    f"- Patch manifest: {patch_manifest_path}",
                    f"- Blockers: {', '.join(blockers)}",
                    "",
                    "No Google Board, DB, Kaspi, Telegram, scheduler, or external write happened.",
                    "",
                ]
            ),
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    patch_manifest_sha = sha256_file(patch_manifest_path)
    patch_rows_sha = sha256_file(patch_rows_path)
    target_tab = str(patch_rows[0].get("target_tab") or "SalesRaw_Today")
    source_column = str(patch_rows[0].get("source_column") or "MY_SIZE")
    approval = _approval_phrase(
        patch_manifest_path=patch_manifest_path,
        patch_manifest_sha=patch_manifest_sha,
        patch_rows_path=patch_rows_path,
        patch_rows_sha=patch_rows_sha,
        patch_rows_count=len(patch_rows),
        target_tab=target_tab,
        source_column=source_column,
    )
    redacted_rows = _redacted_rows(patch_rows)
    redacted_rows_json = json.dumps(redacted_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _write_json(output_dir / "google_board_my_size_apply_rows_redacted.json", redacted_rows)
    _write_text(output_dir / "REQUIRED_EXACT_GOOGLE_BOARD_MY_SIZE_APPLY_APPROVAL_PHRASE.txt", approval + "\n")
    handoff_path = output_dir / "KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF.md"
    starter_path = output_dir / "ONE_SENTENCE_STARTER_PROMPT.txt"
    _write_text(
        handoff_path,
        _build_handoff(
            output_dir=output_dir,
            patch_manifest_path=patch_manifest_path,
            patch_rows_path=patch_rows_path,
            patch_rows=patch_rows,
            approval_phrase=approval,
        ),
    )
    _write_text(
        starter_path,
        (
            f"Read {handoff_path}, wait for the exact owner approval phrase inside it, "
            "apply only the prepared SalesRaw_Today.MY_SIZE patch rows to Google Board, "
            "run readback/dry-run follow-up gates, and stop before DB/Telegram/waybill apply."
        )
        + "\n",
    )
    manifest = {
        "gate": "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "patch_manifest_path": str(patch_manifest_path),
        "patch_manifest_sha256": patch_manifest_sha,
        "patch_rows_path": str(patch_rows_path),
        "patch_rows_sha256": patch_rows_sha,
        "patch_rows_count": len(patch_rows),
        "target_tab": target_tab,
        "source_column": source_column,
        "redacted_apply_rows_sha256": hashlib.sha256(redacted_rows_json).hexdigest(),
        "approval_phrase_generated": True,
        "approval_phrase_path": str(output_dir / "REQUIRED_EXACT_GOOGLE_BOARD_MY_SIZE_APPLY_APPROVAL_PHRASE.txt"),
        "handoff_path": str(handoff_path),
        "starter_prompt_path": str(starter_path),
        "google_board_write_allowed_now": False,
        "requires_exact_owner_approval_before_write": True,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Google Board MY_SIZE Apply Handoff",
                "",
                f"Gate: {manifest['gate']}",
                "",
                f"- Patch rows: {len(patch_rows)}",
                f"- Approval phrase: {manifest['approval_phrase_path']}",
                f"- Handoff: {handoff_path}",
                "- Google Board write performed: false",
                "- Requires exact owner approval before write: true",
                "",
            ]
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
