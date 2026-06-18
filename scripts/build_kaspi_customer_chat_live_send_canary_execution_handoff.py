#!/usr/bin/env python3
"""Build a helper-agent handoff for the one-order Kaspi live-send canary.

This is not a sender. It only packages the execution instructions after the
approval packet is already GREEN and the owner has an exact phrase to approve.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    STORE_MERCHANT_ACCOUNT_IDS,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
GREEN_APPROVAL_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _default_output_dir(approval_dir: Path) -> Path:
    return approval_dir / "live_send_execution_handoff"


def _load_phrase(approval_dir: Path) -> str:
    phrase_path = approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    if not phrase_path.exists():
        return ""
    return phrase_path.read_text(encoding="utf-8").strip()


def _blocked_manifest(
    *,
    approval_dir: Path,
    output_dir: Path,
    approval_manifest: dict[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "gate": "YELLOW_LIVE_SEND_EXECUTION_HANDOFF_BLOCKED_APPROVAL_NOT_GREEN",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "output_dir": str(output_dir),
        "approval_gate": (approval_manifest or {}).get("gate"),
        "blockers": blockers,
        "handoff_generated": False,
        "customer_send_allowed_now": False,
        "requires_exact_owner_approval_before_send": True,
        "kaspi_chat_write_allowed_by_this_script": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }


def _build_handoff(
    *,
    approval_dir: Path,
    output_dir: Path,
    approval_manifest: dict[str, Any],
    approval_phrase: str,
) -> str:
    packet_manifest_path = approval_manifest.get("packet_manifest_path")
    packet_dir = approval_manifest.get("packet_dir")
    validation_path = approval_manifest.get("live_ui_validation_json")
    selected_order_ref = approval_manifest.get("selected_order_ref")
    selected_db_row_id = approval_manifest.get("selected_db_row_id")
    selected_store_code = approval_manifest.get("selected_store_code")
    expected_merchant_account_id = approval_manifest.get("expected_merchant_account_id")
    selected_status_filter = approval_manifest.get("selected_status_filter")
    template_hash = approval_manifest.get("template_hash")
    selector_map_lines = [
        f"- `{store} -> ID - {merchant_id}`"
        for store, merchant_id in sorted(STORE_MERCHANT_ACCOUNT_IDS.items())
    ]
    return "\n".join(
        [
            "# Kaspi Customer Size Live Send Canary Execution Handoff",
            "",
            "Gate: GREEN_LIVE_SEND_EXECUTION_HANDOFF_READY_NO_SEND_PERFORMED",
            "",
            "## Mission",
            "",
            "Use a UI-capable helper runtime only after the human owner pastes the exact approval phrase below. Send exactly one Kaspi merchant-chat size-request template to the selected redacted canary order, then record redacted proof and stop.",
            "",
            "This handoff does not itself authorize sending. It packages the future execution path.",
            "",
            "## Bootstrap",
            "",
            f"1. Read `~/Docs/Autonomous_business/AGENTS.md`.",
            f"2. Read this handoff: `{output_dir / 'KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md'}`.",
            f"3. Read approval manifest: `{approval_dir / 'manifest.json'}`.",
            f"4. Read source packet manifest: `{packet_manifest_path}`.",
            f"5. Read no-send validation: `{validation_path}`.",
            "",
            "## Required Exact Owner Approval",
            "",
            "Do not send anything until this exact approval phrase is present in the agent chat/task:",
            "",
            "```text",
            approval_phrase,
            "```",
            "",
            "## Selected Redacted Target",
            "",
            f"- Source packet: `{packet_dir}`",
            f"- Approval dir: `{approval_dir}`",
            f"- Store: `{selected_store_code}`",
            f"- Expected Kaspi merchant account ID: `{expected_merchant_account_id}`",
            f"- DB row: `{selected_db_row_id}`",
            f"- Selected order ref: `{selected_order_ref}`",
            f"- Merchant status filter: `{selected_status_filter}`",
            f"- Template hash: `{template_hash}`",
            "",
            "## Store-Scoped Merchant Selector Rule",
            "",
            "Before searching any order, choose the merchant account that belongs to that order's store. Never search a target order under a different currently-selected merchant account just because the dropdown is already open.",
            "",
            "Current required selector:",
            "",
            f"- `{selected_store_code} -> ID - {expected_merchant_account_id}`",
            "",
            "Full selector map:",
            "",
            *selector_map_lines,
            "",
            "If the visible selector cannot be proven as the required ID, stop YELLOW before searching and preserve the browser session.",
            "",
            "## Session Preservation",
            "",
            "Reuse the already-open resident/browser session whenever possible. Do not close Chrome, do not close the persistent profile, do not use `--allow-session-close`, and do not force a fresh login/SMS cycle. If Kaspi shows login/SMS, preserve the window and stop with a session-preservation blocker unless the owner is actively present to complete that one login.",
            "",
            "## Runtime-Only Raw Order Resolution",
            "",
            "Resolve the raw order ID only at browser action time and use it only in the Kaspi merchant order search field. Do not write it to terminal logs, Markdown, JSON, screenshots, chat, or closeouts.",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "RAW_ORDER_ID=\"$(",
            "  PYTHONPATH=. .venv/bin/python scripts/resolve_kaspi_customer_chat_canary_runtime_secret.py \\",
            f"    --packet-manifest {packet_manifest_path} \\",
            f"    --audit-json {packet_dir}/runtime_secret_resolver_audit_redacted.json \\",
            "    --print-raw-order-id",
            ")\"",
            "printf '%s' \"$RAW_ORDER_ID\" | pbcopy",
            "unset RAW_ORDER_ID",
            "```",
            "",
            "## Allowed UI Actions",
            "",
            f"- Select/confirm the visible Kaspi merchant account dropdown is `ID - {expected_merchant_account_id}` for store `{selected_store_code}` before searching and again after any page navigation.",
            "- Open the selected merchant status/order filter.",
            "- Search the raw order ID from clipboard.",
            "- Open the customer-message UI for that exact order.",
            "- Type exactly the approved template once.",
            "- Send exactly once.",
            "- Observe redacted send confirmation.",
            "",
            "## Forbidden Actions",
            "",
            "- No second order, bulk sends, retries, or unrelated customer messages.",
            "- No direct Kaspi chat API write.",
            "- No raw order ID/customer text/phone/address/cookies/tokens/session export.",
            "- No browser/session teardown, no forced relogin, and no `--allow-session-close`.",
            "- No Google Board, production DB, CRM workbook, Telegram, WhatsApp, scheduler, or workbook write.",
            "",
            "## Required Result Files",
            "",
            f"Write `{approval_dir}/live_send_canary_result_redacted.json` with:",
            "",
            "```json",
            json.dumps(
                {
                    "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
                    "selected_order_ref": selected_order_ref,
                    "selected_db_row_id": selected_db_row_id,
                    "selected_store_code": selected_store_code,
                    "selected_status_filter": selected_status_filter,
                    "template_hash": template_hash,
                    "merchant_account_match_proven": True,
                    "visible_merchant_selector_id": expected_merchant_account_id,
                    "store_scoped_selector_map_applied": True,
                    "browser_session_preserved": True,
                    "order_search_performed": True,
                    "chat_opened": True,
                    "message_text_typed": True,
                    "message_sent": True,
                    "send_confirmation_observed": True,
                    "sent_count": 1,
                    "other_customer_messages_sent": False,
                    "raw_order_id_exported": False,
                    "raw_customer_text_exported": False,
                    "raw_phone_exported": False,
                    "cookie_token_session_exported": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            f"Write `{approval_dir}/live_send_canary_closeout.md` with standalone gate:",
            "",
            "```text",
            "Gate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
            "```",
            "",
            "## Final Validator",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "PYTHONPATH=. .venv/bin/python scripts/validate_kaspi_customer_chat_live_send_canary_result.py \\",
            f"  --approval-dir {approval_dir} \\",
            f"  --output-json {approval_dir}/live_send_canary_result_validation.json \\",
            "  --require-green",
            "```",
            "",
            "If the validator is not `GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER`, stop and report the exact blocker. Do not retry sends.",
            "",
            "## Post-Send Local Ledger Bridge",
            "",
            "After the validator is GREEN, record the local ledger transition and reply-poll schedule. This bridge does not send another message and does not write Kaspi, Google Board, production DB, Telegram, scheduler, or workbook state.",
            "",
            "```bash",
            "cd ~/Docs/Autonomous_business",
            "PYTHONPATH=. .venv/bin/python scripts/record_kaspi_customer_size_live_send_canary_acceptance.py \\",
            f"  --approval-dir {approval_dir} \\",
            "  --ledger-db runtime/customer_size_request_ledger/no_send_customer_size_request_ledger.sqlite \\",
            f"  --output-dir {approval_dir}/post_live_send_canary_ledger_bridge",
            "```",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    approval_dir = args.approval_dir.resolve()
    output_dir = (args.output_dir or _default_output_dir(approval_dir)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    approval_manifest_path = approval_dir / "manifest.json"
    blockers: list[str] = []
    approval_manifest: dict[str, Any] | None = None
    if not approval_manifest_path.exists():
        blockers.append("approval_manifest_missing")
    else:
        approval_manifest = _read_json(approval_manifest_path)
        if approval_manifest.get("gate") != GREEN_APPROVAL_GATE:
            blockers.append("approval_packet_not_green")
    approval_phrase = _load_phrase(approval_dir)
    if not approval_phrase:
        blockers.append("approval_phrase_missing")

    if blockers:
        manifest = _blocked_manifest(
            approval_dir=approval_dir,
            output_dir=output_dir,
            approval_manifest=approval_manifest,
            blockers=blockers,
        )
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(
            output_dir / "closeout.md",
            "\n".join(
                [
                    "# Kaspi Customer Size Live Send Canary Execution Handoff",
                    "",
                    f"Gate: {manifest['gate']}",
                    "",
                    f"- Approval dir: {approval_dir}",
                    f"- Blockers: {len(blockers)}",
                    "",
                    "No handoff was generated because the live-send approval packet is not ready.",
                    "No customer message, Kaspi write, Google Board write, DB write, Telegram send, or external write happened.",
                    "",
                ]
            ),
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    assert approval_manifest is not None
    handoff = _build_handoff(
        approval_dir=approval_dir,
        output_dir=output_dir,
        approval_manifest=approval_manifest,
        approval_phrase=approval_phrase,
    )
    handoff_path = output_dir / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    starter_path = output_dir / "ONE_SENTENCE_STARTER_PROMPT.txt"
    _write_text(handoff_path, handoff)
    _write_text(
        starter_path,
        (
            "Read "
            f"{handoff_path} and execute the one-order Kaspi live-send canary only after "
            "the exact owner approval phrase inside that handoff is present; preserve the existing "
            "browser session, prove the order store's exact merchant selector before search, send exactly once, "
            "record redacted proof, run the validator, and stop."
        )
        + "\n",
    )
    manifest = {
        "gate": "GREEN_LIVE_SEND_EXECUTION_HANDOFF_READY_NO_SEND_PERFORMED",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "output_dir": str(output_dir),
        "handoff_path": str(handoff_path),
        "starter_prompt_path": str(starter_path),
        "approval_gate": approval_manifest.get("gate"),
        "approval_phrase_included": True,
        "selected_order_ref": approval_manifest.get("selected_order_ref"),
        "selected_db_row_id": approval_manifest.get("selected_db_row_id"),
        "selected_store_code": approval_manifest.get("selected_store_code"),
        "merchant_selector_map": STORE_MERCHANT_ACCOUNT_IDS,
        "customer_send_allowed_now": False,
        "requires_exact_owner_approval_before_send": True,
        "kaspi_chat_write_allowed_by_this_script": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Live Send Canary Execution Handoff",
                "",
                f"Gate: {manifest['gate']}",
                "",
                f"- Handoff: {handoff_path}",
                f"- Starter prompt: {starter_path}",
                "- Customer send performed: false",
                "- Requires exact owner approval before send: true",
                "",
            ]
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
