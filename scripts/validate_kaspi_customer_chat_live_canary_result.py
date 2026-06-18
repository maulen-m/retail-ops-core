#!/usr/bin/env python3
"""Validate a redacted Kaspi customer-chat live UI no-send canary result."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_canary_packet_2026-06-16_20260616_125511_final"
)
GREEN_RESULT_GATE = "GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND"
ACCEPTED_GATE = "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"


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


def _load_raw_order_id_for_scan(manifest: dict[str, Any]) -> str | None:
    db_path = Path(str(manifest.get("db_path") or ""))
    db_row_id = manifest.get("selected_db_row_id")
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


def _scan_packet_for_prohibited_values(
    packet_dir: Path,
    *,
    raw_order_id: str | None,
    output_json: Path | None,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
    )
    for path in sorted(packet_dir.rglob("*")):
        if not path.is_file():
            continue
        if output_json and path.resolve() == output_json.resolve():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if raw_order_id and raw_order_id in text:
            violations.append({"path": str(path), "violation": "raw_order_id"})
        if phone_pattern.search(text):
            violations.append({"path": str(path), "violation": "phone_like"})
    return violations


def _closeout_has_gate(path: Path, gate: str) -> bool:
    if not path.exists():
        return False
    pattern = re.compile(rf"^Gate:\s*{re.escape(gate)}\s*$", re.MULTILINE)
    return bool(pattern.search(path.read_text(encoding="utf-8", errors="ignore")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="Exit nonzero unless the live no-send canary result is accepted GREEN.",
    )
    return parser


def validate(args: argparse.Namespace) -> dict[str, Any]:
    packet_dir = args.packet_dir.resolve()
    manifest_path = packet_dir / "manifest.json"
    audit_path = packet_dir / "runtime_secret_resolver_audit_redacted.json"
    result_path = args.result_json or (packet_dir / "live_ui_probe_result_redacted.json")
    closeout_path = args.closeout_md or (packet_dir / "live_ui_no_send_probe_closeout.md")
    output_json = args.output_json.resolve() if args.output_json else None

    checks: dict[str, Any] = {
        "packet_dir_exists": packet_dir.exists(),
        "manifest_exists": manifest_path.exists(),
        "runtime_audit_exists": audit_path.exists(),
        "result_exists": result_path.exists(),
        "closeout_exists": closeout_path.exists(),
    }
    validation: dict[str, Any] = {
        "gate": "YELLOW_LIVE_UI_RESULT_MISSING",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(packet_dir),
        "manifest_path": str(manifest_path),
        "runtime_audit_path": str(audit_path),
        "result_json_path": str(result_path),
        "closeout_md_path": str(closeout_path),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "checks": checks,
        "blockers": [],
        "violations": [],
    }

    if not manifest_path.exists():
        validation["gate"] = "RED_LIVE_UI_CANARY_MANIFEST_MISSING"
        validation["blockers"].append("manifest_missing")
        return validation
    manifest = _read_json(manifest_path)
    validation["selected_order_ref"] = manifest.get("selected_order_ref")
    validation["selected_store_code"] = manifest.get("selected_store_code")
    validation["selected_status_filter"] = manifest.get("selected_status_filter")
    validation["selected_db_row_id"] = manifest.get("selected_db_row_id")

    raw_order_id = _load_raw_order_id_for_scan(manifest)
    scan_violations = _scan_packet_for_prohibited_values(
        packet_dir,
        raw_order_id=raw_order_id,
        output_json=output_json,
    )
    if scan_violations:
        validation["gate"] = "RED_LIVE_UI_CANARY_REDACTION_SCAN_FAILED"
        validation["violations"] = scan_violations
        validation["blockers"].append("redaction_scan_failed")
        return validation
    checks["redaction_scan_passed"] = True

    if not audit_path.exists():
        validation["gate"] = "YELLOW_RUNTIME_SECRET_AUDIT_MISSING"
        validation["blockers"].append("runtime_secret_audit_missing")
        return validation
    audit = _read_json(audit_path)
    checks["runtime_audit_gate"] = audit.get("gate")
    checks["runtime_audit_db_unchanged"] = audit.get("db_unchanged")
    checks["runtime_audit_candidate_still_missing_size"] = audit.get("candidate_still_missing_size")
    if audit.get("gate") != "GREEN_RUNTIME_SECRET_RESOLVED_REDACTED_AUDIT":
        validation["gate"] = "YELLOW_RUNTIME_SECRET_AUDIT_NOT_GREEN"
        validation["blockers"].append("runtime_secret_audit_not_green")
        return validation
    if audit.get("raw_order_id_exported") is not False or audit.get("raw_customer_text_exported") is not False:
        validation["gate"] = "RED_RUNTIME_SECRET_AUDIT_UNSAFE"
        validation["blockers"].append("runtime_secret_audit_raw_export_flag")
        return validation
    if audit.get("candidate_still_missing_size") is not True:
        validation["gate"] = "YELLOW_RUNTIME_SECRET_CANDIDATE_NOT_CURRENT"
        validation["blockers"].append("runtime_secret_candidate_not_current")
        return validation

    if not result_path.exists():
        validation["gate"] = "YELLOW_LIVE_UI_RESULT_MISSING"
        validation["blockers"].append("live_ui_probe_result_missing")
        return validation
    result = _read_json(result_path)
    checks["result_gate"] = result.get("gate")
    checks["closeout_has_green_gate"] = _closeout_has_gate(closeout_path, GREEN_RESULT_GATE)
    checks["closeout_has_result_gate"] = _closeout_has_gate(
        closeout_path,
        str(result.get("gate") or ""),
    )

    required_true = [
        "merchant_account_match_proven",
        "order_search_performed",
        "order_detail_or_result_reached",
        "chat_button_present",
    ]
    required_false = [
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
    ]
    missing_true = [key for key in required_true if _bool_value(result, key) is not True]
    unsafe_true = [key for key in required_false if _bool_value(result, key) is not False]
    checks["required_true_missing"] = missing_true
    checks["unsafe_false_fields_true_or_missing"] = unsafe_true

    if result.get("gate") != GREEN_RESULT_GATE:
        validation["gate"] = "YELLOW_LIVE_UI_RESULT_NOT_GREEN"
        validation["blockers"].append("live_ui_result_not_green")
    if missing_true:
        validation["gate"] = "YELLOW_LIVE_UI_RESULT_INCOMPLETE"
        validation["blockers"].append("live_ui_required_proof_missing")
    if unsafe_true:
        validation["gate"] = "RED_LIVE_UI_RESULT_UNSAFE"
        validation["blockers"].append("live_ui_unsafe_flags")
    if result.get("gate") == GREEN_RESULT_GATE:
        if not closeout_path.exists() or not checks["closeout_has_green_gate"]:
            validation["gate"] = "YELLOW_LIVE_UI_CLOSEOUT_MISSING_GREEN_GATE"
            validation["blockers"].append("live_ui_closeout_missing_green_gate")
    elif not closeout_path.exists() or not checks["closeout_has_result_gate"]:
        validation["gate"] = "YELLOW_LIVE_UI_CLOSEOUT_MISSING_RESULT_GATE"
        validation["blockers"].append("live_ui_closeout_missing_result_gate")

    if not validation["blockers"]:
        validation["gate"] = ACCEPTED_GATE
        validation["accepted"] = True
    else:
        validation["accepted"] = False
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
