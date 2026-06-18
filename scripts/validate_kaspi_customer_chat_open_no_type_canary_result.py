#!/usr/bin/env python3
"""Validate a redacted Kaspi open-chat/no-type side-effect canary result."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_canary_current_20260618_1549_no_send"
)
PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
RESULT_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_COMPLETED_NO_SEND"
ACCEPTED_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND"
RESULT_MISSING_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _closeout_has_gate(path: Path, gate: str) -> bool:
    if not path.exists():
        return False
    pattern = re.compile(rf"^Gate:\s*{re.escape(gate)}\s*$", re.MULTILINE)
    return bool(pattern.search(path.read_text(encoding="utf-8", errors="ignore")))


def _bool_value(row: dict[str, Any], key: str) -> bool:
    return bool(row.get(key))


def _scan_for_prohibited_values(paths: list[Path]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
    )
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        label_safe = (
            text.replace("raw_session_material_exported", "safe_session_export_flag")
            .replace("cookie_token_session_exported", "safe_session_export_flag")
            .replace("session material", "safe session label")
            .replace("session_material", "safe_session_label")
        )
        if phone_pattern.search(text):
            violations.append({"path": str(path), "violation": "phone_like"})
        for forbidden in ["authorization", "bearer", "localStorage", "sessionStorage", "cookie"]:
            if forbidden.lower() in label_safe.lower():
                violations.append({"path": str(path), "violation": f"session_label:{forbidden}"})
    return violations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=CURRENT_PACKET_DIR)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="Exit nonzero unless the open-chat/no-type canary result is accepted GREEN.",
    )
    return parser


def validate(args: argparse.Namespace) -> dict[str, Any]:
    packet_dir = args.packet_dir.resolve()
    packet_manifest_path = packet_dir / "manifest.json"
    result_path = (args.result_json or packet_dir / "open_chat_no_type_result_redacted.json").resolve()
    closeout_path = (args.closeout_md or packet_dir / "open_chat_no_type_canary_closeout.md").resolve()
    output_json = args.output_json.resolve() if args.output_json else None
    validation: dict[str, Any] = {
        "gate": RESULT_MISSING_GATE,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(packet_dir),
        "packet_manifest_path": str(packet_manifest_path),
        "result_json_path": str(result_path),
        "closeout_md_path": str(closeout_path),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "message_text_typed": False,
        "message_sent": False,
        "blockers": [],
        "violations": [],
        "warnings": [],
        "checks": {
            "packet_manifest_exists": packet_manifest_path.exists(),
            "result_exists": result_path.exists(),
            "closeout_exists": closeout_path.exists(),
        },
    }
    if not packet_manifest_path.exists():
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_PACKET_MANIFEST_MISSING"
        validation["blockers"].append("packet_manifest_missing")
        return validation

    packet = _read_json(packet_manifest_path)
    validation["selected_order_ref"] = packet.get("selected_order_ref")
    validation["selected_db_row_id"] = packet.get("selected_db_row_id")
    validation["selected_store_code"] = packet.get("selected_store_code")
    validation["selected_status_filter"] = packet.get("selected_status_filter")
    validation["expected_merchant_account_id"] = packet.get("expected_merchant_account_id")
    validation["checks"]["packet_gate"] = packet.get("gate")
    if packet.get("gate") != PACKET_GREEN_GATE:
        validation["gate"] = "YELLOW_OPEN_CHAT_NO_TYPE_PACKET_NOT_GREEN"
        validation["blockers"].append("packet_not_green")
        return validation

    lock_path = Path(str(packet.get("packet_manifest_path") or ""))
    expected_lock_sha = str(packet.get("packet_manifest_sha256") or "")
    validation["checks"]["packet_lock_path"] = str(lock_path)
    validation["checks"]["packet_lock_sha256"] = expected_lock_sha
    if not lock_path.exists():
        validation["gate"] = "YELLOW_OPEN_CHAT_NO_TYPE_PACKET_LOCK_MISSING"
        validation["blockers"].append("packet_lock_missing")
        return validation
    if expected_lock_sha and _sha256_file(lock_path) != expected_lock_sha:
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_PACKET_LOCK_SHA_MISMATCH"
        validation["blockers"].append("packet_lock_sha_mismatch")
        return validation

    if not result_path.exists():
        validation["gate"] = RESULT_MISSING_GATE
        validation["blockers"].append("open_chat_no_type_result_missing")
        return validation

    scan_paths = [result_path, closeout_path]
    if output_json:
        scan_paths = [path for path in scan_paths if path.resolve() != output_json]
    violations = _scan_for_prohibited_values(scan_paths)
    if violations:
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_REDACTION_SCAN_FAILED"
        validation["violations"] = violations
        validation["blockers"].append("redaction_scan_failed")
        return validation

    result = _read_json(result_path)
    validation["checks"]["result_gate"] = result.get("gate")
    validation["checks"]["closeout_has_green_gate"] = _closeout_has_gate(
        closeout_path,
        RESULT_GREEN_GATE,
    )
    required_true = [
        "merchant_account_match_proven",
        "order_search_performed",
        "chat_opened",
        "browser_session_preserved",
    ]
    required_false = [
        "message_text_typed",
        "message_sent",
        "customer_send_performed",
        "kaspi_chat_write_performed",
        "send_message_route_observed",
        "typing_send_text_route_observed",
        "start_chat_route_observed",
        "other_customer_messages_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
        "cookie_token_session_exported",
    ]
    missing_true = [key for key in required_true if _bool_value(result, key) is not True]
    unsafe_true = [key for key in required_false if _bool_value(result, key) is not False]
    validation["checks"]["required_true_missing"] = missing_true
    validation["checks"]["unsafe_false_fields_true_or_missing"] = unsafe_true
    validation["checks"]["message_status_change_route_observed"] = _bool_value(
        result,
        "message_status_change_route_observed",
    )
    validation["checks"]["load_more_messages_route_observed"] = _bool_value(
        result,
        "load_more_messages_route_observed",
    )
    if validation["checks"]["message_status_change_route_observed"]:
        validation["warnings"].append("message_status_change_route_observed")
    if validation["checks"]["load_more_messages_route_observed"]:
        validation["warnings"].append("load_more_messages_route_observed")

    if result.get("gate") != RESULT_GREEN_GATE:
        validation["gate"] = "YELLOW_OPEN_CHAT_NO_TYPE_RESULT_NOT_GREEN"
        validation["blockers"].append("result_not_green")
    if result.get("selected_order_ref") != packet.get("selected_order_ref"):
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_ORDER_REF_MISMATCH"
        validation["blockers"].append("selected_order_ref_mismatch")
    if str(result.get("selected_db_row_id") or "") != str(packet.get("selected_db_row_id") or ""):
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_DB_ROW_MISMATCH"
        validation["blockers"].append("selected_db_row_id_mismatch")
    if result.get("selected_store_code") != packet.get("selected_store_code"):
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_STORE_MISMATCH"
        validation["blockers"].append("selected_store_code_mismatch")
    expected_selector_id = str(packet.get("expected_merchant_account_id") or "").strip()
    visible_selector_id = str(result.get("visible_merchant_selector_id") or "").strip()
    validation["checks"]["visible_merchant_selector_id"] = visible_selector_id
    validation["checks"]["expected_merchant_account_id"] = expected_selector_id
    if expected_selector_id and visible_selector_id != expected_selector_id:
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_VISIBLE_MERCHANT_SELECTOR_MISMATCH"
        validation["blockers"].append("visible_merchant_selector_id_mismatch")
    if missing_true:
        validation["gate"] = "YELLOW_OPEN_CHAT_NO_TYPE_RESULT_INCOMPLETE"
        validation["blockers"].append("required_open_proof_missing")
    if unsafe_true:
        validation["gate"] = "RED_OPEN_CHAT_NO_TYPE_UNSAFE_FLAGS"
        validation["blockers"].append("unsafe_flags")
    if not closeout_path.exists() or not validation["checks"]["closeout_has_green_gate"]:
        validation["gate"] = "YELLOW_OPEN_CHAT_NO_TYPE_CLOSEOUT_MISSING_GREEN_GATE"
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
