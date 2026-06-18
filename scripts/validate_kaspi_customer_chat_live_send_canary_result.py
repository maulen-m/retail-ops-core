#!/usr/bin/env python3
"""Validate a redacted one-order Kaspi customer-size live send canary result."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_DIR = REPO_ROOT / "exports" / "validation"
GREEN_RESULT_GATE = "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER"
ACCEPTED_GATE = "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bool_value(row: dict[str, Any], key: str) -> bool:
    return bool(row.get(key))


def _closeout_has_gate(path: Path, gate: str) -> bool:
    if not path.exists():
        return False
    pattern = re.compile(rf"^Gate:\s*{re.escape(gate)}\s*$", re.MULTILINE)
    return bool(pattern.search(path.read_text(encoding="utf-8", errors="ignore")))


def _load_raw_order_id_for_scan(approval_manifest: dict[str, Any]) -> str | None:
    packet_manifest_value = str(approval_manifest.get("packet_manifest_path") or "").strip()
    if not packet_manifest_value:
        return None
    packet_manifest_path = Path(packet_manifest_value)
    if not packet_manifest_path.is_file():
        return None
    packet_manifest = _read_json(packet_manifest_path)
    db_path_value = str(packet_manifest.get("db_path") or "").strip()
    if not db_path_value:
        return None
    db_path = Path(db_path_value)
    db_row_id = packet_manifest.get("selected_db_row_id")
    if not db_path.exists() or db_row_id is None:
        return None
    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT order_id FROM fact_orders_kaspi WHERE id = ?",
            (int(db_row_id),),
        ).fetchone()
    if not row:
        return None
    return str(row[0] or "").strip() or None


def _scan_for_prohibited_values(
    root: Path,
    *,
    raw_order_id: str | None,
    output_json: Path | None,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    phone_scan_names = {
        "live_send_canary_result_redacted.json",
        "live_send_canary_closeout.md",
        "live_send_canary_result_validation.json",
    }
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
    )
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if output_json and path.resolve() == output_json.resolve():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if raw_order_id and raw_order_id in text:
            violations.append({"path": str(path), "violation": "raw_order_id"})
        if path.name in phone_scan_names and phone_pattern.search(text):
            violations.append({"path": str(path), "violation": "phone_like"})
    return violations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="Exit nonzero unless the live send canary result is accepted GREEN.",
    )
    return parser


def validate(args: argparse.Namespace) -> dict[str, Any]:
    approval_dir = args.approval_dir.resolve()
    approval_manifest_path = approval_dir / "manifest.json"
    result_path = args.result_json or (approval_dir / "live_send_canary_result_redacted.json")
    closeout_path = args.closeout_md or (approval_dir / "live_send_canary_closeout.md")
    output_json = args.output_json.resolve() if args.output_json else None
    validation: dict[str, Any] = {
        "gate": "YELLOW_LIVE_SEND_CANARY_RESULT_MISSING",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "approval_manifest_path": str(approval_manifest_path),
        "result_json_path": str(result_path),
        "closeout_md_path": str(closeout_path),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "blockers": [],
        "violations": [],
        "checks": {
            "approval_manifest_exists": approval_manifest_path.exists(),
            "result_exists": result_path.exists(),
            "closeout_exists": closeout_path.exists(),
        },
    }
    if not approval_manifest_path.exists():
        validation["gate"] = "RED_LIVE_SEND_CANARY_APPROVAL_MANIFEST_MISSING"
        validation["blockers"].append("approval_manifest_missing")
        return validation
    approval_manifest = _read_json(approval_manifest_path)
    validation["selected_order_ref"] = approval_manifest.get("selected_order_ref")
    validation["selected_db_row_id"] = approval_manifest.get("selected_db_row_id")
    validation["selected_store_code"] = approval_manifest.get("selected_store_code")
    validation["template_hash"] = approval_manifest.get("template_hash")
    validation["expected_merchant_account_id"] = approval_manifest.get("expected_merchant_account_id")
    validation["checks"]["approval_gate"] = approval_manifest.get("gate")
    validation["checks"]["approval_phrase_generated"] = approval_manifest.get(
        "approval_phrase_generated"
    )

    raw_order_id = _load_raw_order_id_for_scan(approval_manifest)
    scan_violations = _scan_for_prohibited_values(
        approval_dir,
        raw_order_id=raw_order_id,
        output_json=output_json,
    )
    if scan_violations:
        validation["gate"] = "RED_LIVE_SEND_CANARY_REDACTION_SCAN_FAILED"
        validation["violations"] = scan_violations
        validation["blockers"].append("redaction_scan_failed")
        return validation
    validation["checks"]["redaction_scan_passed"] = True

    if approval_manifest.get("gate") != "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND":
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_APPROVAL_NOT_GREEN"
        validation["blockers"].append("approval_packet_not_green")
        return validation
    if approval_manifest.get("approval_phrase_generated") is not True:
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_APPROVAL_PHRASE_MISSING"
        validation["blockers"].append("approval_phrase_missing")
        return validation
    if not result_path.exists():
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_RESULT_MISSING"
        validation["blockers"].append("live_send_result_missing")
        return validation

    result = _read_json(result_path)
    validation["checks"]["result_gate"] = result.get("gate")
    validation["checks"]["closeout_has_green_gate"] = _closeout_has_gate(
        closeout_path,
        GREEN_RESULT_GATE,
    )
    required_true = [
        "merchant_account_match_proven",
        "order_search_performed",
        "chat_opened",
        "message_text_typed",
        "message_sent",
        "send_confirmation_observed",
        "store_scoped_selector_map_applied",
        "browser_session_preserved",
    ]
    required_false = [
        "other_customer_messages_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "cookie_token_session_exported",
    ]
    missing_true = [key for key in required_true if _bool_value(result, key) is not True]
    unsafe_true = [key for key in required_false if _bool_value(result, key) is not False]
    validation["checks"]["required_true_missing"] = missing_true
    validation["checks"]["unsafe_false_fields_true_or_missing"] = unsafe_true

    if result.get("gate") != GREEN_RESULT_GATE:
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_RESULT_NOT_GREEN"
        validation["blockers"].append("live_send_result_not_green")
    if result.get("selected_order_ref") != approval_manifest.get("selected_order_ref"):
        validation["gate"] = "RED_LIVE_SEND_CANARY_ORDER_REF_MISMATCH"
        validation["blockers"].append("selected_order_ref_mismatch")
    if result.get("template_hash") != approval_manifest.get("template_hash"):
        validation["gate"] = "RED_LIVE_SEND_CANARY_TEMPLATE_HASH_MISMATCH"
        validation["blockers"].append("template_hash_mismatch")
    expected_selector_id = str(approval_manifest.get("expected_merchant_account_id") or "").strip()
    visible_selector_id = str(result.get("visible_merchant_selector_id") or "").strip()
    validation["checks"]["visible_merchant_selector_id"] = visible_selector_id
    validation["checks"]["expected_merchant_account_id"] = expected_selector_id
    if expected_selector_id and visible_selector_id != expected_selector_id:
        validation["gate"] = "RED_LIVE_SEND_CANARY_VISIBLE_MERCHANT_SELECTOR_MISMATCH"
        validation["blockers"].append("visible_merchant_selector_id_mismatch")
    if int(result.get("sent_count") or 0) != 1:
        validation["gate"] = "RED_LIVE_SEND_CANARY_SENT_COUNT_NOT_ONE"
        validation["blockers"].append("sent_count_not_one")
    if missing_true:
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_RESULT_INCOMPLETE"
        validation["blockers"].append("required_send_proof_missing")
    if unsafe_true:
        validation["gate"] = "RED_LIVE_SEND_CANARY_UNSAFE_FLAGS"
        validation["blockers"].append("unsafe_flags")
    if not closeout_path.exists() or not validation["checks"]["closeout_has_green_gate"]:
        validation["gate"] = "YELLOW_LIVE_SEND_CANARY_CLOSEOUT_MISSING_GREEN_GATE"
        validation["blockers"].append("closeout_missing_green_gate")

    validation["accepted"] = not validation["blockers"]
    if validation["accepted"]:
        validation["gate"] = ACCEPTED_GATE
    return validation


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validation = validate(args)
    if args.output_json:
        _write_json(args.output_json, validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and validation.get("gate") != ACCEPTED_GATE:
        return 1
    if str(validation.get("gate", "")).startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
