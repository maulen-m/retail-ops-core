#!/usr/bin/env python3
"""Build a redacted live UI no-send canary packet for Kaspi customer chat.

The packet is a handoff artifact for a browser/computer-use agent. It never
exports raw order IDs; the browser agent must resolve the raw order ID locally
from db_row_id at execution time and must not write it into evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ops.customer_size_request import (
    KASPI_MERCHANT_ORDERS_BASE_URL,
    build_live_ui_canary_targets,
    load_missing_size_candidates,
    private_hash,
    sha256_file,
    suggest_merchant_status_filter,
)


DEFAULT_DB = REPO_ROOT / "db" / "app.db"


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_chat_live_canary_packet_{target_date.isoformat()}_{stamp}"
    )


def _choose_candidate(candidates: list[Any], store_priority: list[str], db_row_id: int | None) -> Any:
    if db_row_id is not None:
        for candidate in candidates:
            if candidate.db_row_id == db_row_id:
                return candidate
        raise RuntimeError(f"No current missing-size candidate found for db_row_id={db_row_id}")

    normalized_priority = [store.strip().upper() for store in store_priority if store.strip()]
    if normalized_priority:
        for store in normalized_priority:
            for candidate in candidates:
                if str(candidate.store_code or "").strip().upper() == store:
                    return candidate
    if not candidates:
        raise RuntimeError("No active missing-size candidates found for live canary packet")
    return candidates[0]


def _redact_url(url: str) -> str:
    return str(url).replace("refundId=", "refundId=<redacted>")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build redacted live UI no-send canary packet for one Kaspi missing-size order."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[], help="Optional store_code filter.")
    parser.add_argument(
        "--store-priority",
        action="append",
        default=["ACMEWEAR", "UNIVERSAL", "STOREB"],
        help="Preferred store_code order when multiple candidates exist.",
    )
    parser.add_argument("--db-row-id", type=int, default=None)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db.resolve()
    db_sha_before = sha256_file(db_path) if db_path.exists() else None
    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=args.store,
    )
    selected = _choose_candidate(candidates, args.store_priority, args.db_row_id)
    all_targets = build_live_ui_canary_targets([selected])
    target = all_targets[0]
    target["suggested_merchant_orders_url_redacted"] = _redact_url(
        str(target.get("suggested_merchant_orders_url") or KASPI_MERCHANT_ORDERS_BASE_URL)
    )
    target.pop("suggested_merchant_orders_url", None)
    target["raw_order_id_exported"] = False
    target["raw_order_id_lookup_method"] = "read locally from db/app.db by db_row_id during browser run; do not export"
    target["order_search_value_hash"] = private_hash("kaspi_order_id", selected.raw_order_id)
    target["required_selector"] = "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']"
    target["required_text_hint"] = "Сообщения по заказу"
    target["forbidden_actions"] = [
        "open_chat_unless_required_for_selector_visibility",
        "type_customer_message",
        "click_send",
        "direct_chat_api_write",
        "cookie_token_session_export",
    ]

    probe_template = {
        "gate": "YELLOW_NOT_RUN",
        "selected_order_ref": selected.order_ref,
        "db_row_id": selected.db_row_id,
        "store_code": selected.store_code,
        "suggested_merchant_status_filter": suggest_merchant_status_filter(selected),
        "merchant_account_match_proven": False,
        "order_search_performed": False,
        "order_detail_or_result_reached": False,
        "chat_button_selector": "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']",
        "chat_button_present": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "notes": [],
    }

    manifest = {
        "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_PACKET_READY",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "candidate_count": len(candidates),
        "selected_order_ref": selected.order_ref,
        "selected_db_row_id": selected.db_row_id,
        "selected_store_code": selected.store_code,
        "selected_status_filter": suggest_merchant_status_filter(selected),
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "browser_bridge_required": True,
    }

    _write_json(output_dir / "selected_live_ui_canary_target_redacted.json", target)
    _write_json(output_dir / "live_ui_probe_result_template_redacted.json", probe_template)

    db_sha_after = sha256_file(db_path) if db_path.exists() else None
    manifest["db_sha256_after"] = db_sha_after
    manifest["db_unchanged"] = db_sha_before == db_sha_after
    _write_json(output_dir / "manifest.json", manifest)

    handoff = "\n".join(
        [
            "# Kaspi Customer Chat Live UI No-Send Canary Packet",
            "",
            "Gate: GREEN_LIVE_UI_NO_SEND_CANARY_PACKET_READY",
            "",
            f"- Output folder: {output_dir}",
            f"- Selected store: {selected.store_code}",
            f"- Selected db_row_id: {selected.db_row_id}",
            f"- Selected order_ref: {selected.order_ref}",
            f"- Suggested status filter: {suggest_merchant_status_filter(selected)}",
            f"- Merchant URL: {target['suggested_merchant_orders_url_redacted']}",
            "",
            "Execution rule:",
            "",
            "- Resolve the raw order ID locally from `db/app.db` by `db_row_id` only inside the browser run.",
            "- Do not write the raw order ID, customer text, phone, address, cookies, localStorage, or session material into evidence.",
            "- First prove the visible merchant account/store matches the selected store.",
            "- Navigate to the suggested status filter, search the order ID, and observe the customer-message button.",
            "- Stop before typing or sending any message.",
            "",
            "GREEN live proof requires:",
            "",
            "- matching merchant account/store;",
            "- selected status bucket used;",
            "- selected order result/detail reached;",
            "- selector observed: `button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']`;",
            "- zero chat sends and zero customer text entry;",
            "- redacted local closeout.",
            "",
            "If Chrome/Computer Use fails, stop YELLOW and keep this packet as the next handoff.",
            "",
        ]
    )
    (output_dir / "live_ui_no_send_canary_handoff.md").write_text(handoff, encoding="utf-8")

    closeout = "\n".join(
        [
            "# Kaspi Customer Chat Live UI No-Send Canary Packet Closeout",
            "",
            "Gate: GREEN_LIVE_UI_NO_SEND_CANARY_PACKET_READY",
            "",
            f"- Output folder: {output_dir}",
            f"- Candidate count: {len(candidates)}",
            f"- Selected store: {selected.store_code}",
            f"- Selected db_row_id: {selected.db_row_id}",
            f"- Raw order ID exported: False",
            f"- Customer send allowed: False",
            f"- DB unchanged: {db_sha_before == db_sha_after}",
            "",
            "No browser action, customer message, Kaspi UI/API write, Google Board write,",
            "DB write, scheduler change, token/cookie/session export, or external write happened.",
            "",
        ]
    )
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
