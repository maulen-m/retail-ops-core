#!/usr/bin/env python3
"""Apply approved Kaspi customer-size MY_SIZE cells to Google Ops Board.

Default mode is read-only/dry-run. Live Google Board writes require:

- ``--apply``
- exact owner approval phrase from the apply handoff
- ``ENABLE_GOOGLE_OPS_BOARD_WRITE=1``
- ``ENABLE_KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_WRITE=1``

The script updates only individual ``SalesRaw_Today.MY_SIZE`` cells matched by
``_db_row_id`` and verifies live readback after apply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.integrations.google_ops_board import (
    GoogleOpsBoardClient,
    OpsBoardContract,
    _column_letter,
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.ops.customer_size_request import sha256_file
from scripts.google_ops_board_automation_common import GoogleOpsBoardAutomationLock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
GREEN_HANDOFF_GATE = "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE"
GREEN_PATCH_GATE = "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"
TARGET_TAB = "SalesRaw_Today"
KEY_COLUMN = "_db_row_id"
SIZE_COLUMN = "MY_SIZE"
NARROW_WRITE_ENV_GATE = "ENABLE_KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_WRITE"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _clean_cell(value: Any) -> str:
    return str(value or "").strip()


def _latest_apply_handoff_manifest() -> Path | None:
    candidates = sorted(
        DEFAULT_OUTPUT_ROOT.glob("kaspi_customer_size_google_board_apply_handoff_*current/manifest.json")
    )
    if candidates:
        return candidates[-1]
    candidates = sorted(DEFAULT_OUTPUT_ROOT.glob("kaspi_customer_size_google_board_apply_handoff_*/manifest.json"))
    return candidates[-1] if candidates else None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_approval_text(args: argparse.Namespace) -> str:
    if args.owner_approval_text:
        return str(args.owner_approval_text).strip()
    if args.owner_approval_file:
        return Path(args.owner_approval_file).read_text(encoding="utf-8").strip()
    return ""


def _load_matrix_fixture(path: Path) -> list[list[Any]]:
    payload = _read_json(path)
    matrix = payload.get("matrix") if isinstance(payload, dict) else payload
    if not isinstance(matrix, list):
        raise RuntimeError(f"Fixture must contain a matrix list: {path}")
    return matrix


def load_patch_packet_from_handoff(
    handoff_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, Any]], Path, str]:
    handoff_manifest_path = handoff_manifest_path.resolve()
    handoff_manifest = _read_json(handoff_manifest_path)
    blockers: list[str] = []
    if handoff_manifest.get("gate") != GREEN_HANDOFF_GATE:
        blockers.append("apply_handoff_manifest_not_green")

    patch_manifest_path = Path(str(handoff_manifest.get("patch_manifest_path") or "")).expanduser()
    patch_rows_path = Path(str(handoff_manifest.get("patch_rows_path") or "")).expanduser()
    approval_phrase_path = Path(str(handoff_manifest.get("approval_phrase_path") or "")).expanduser()
    if not patch_manifest_path.is_file():
        blockers.append("patch_manifest_missing")
    if not patch_rows_path.is_file():
        blockers.append("patch_rows_missing")
    if not approval_phrase_path.is_file():
        blockers.append("approval_phrase_file_missing")
    if blockers:
        raise RuntimeError(",".join(blockers))

    patch_manifest = _read_json(patch_manifest_path)
    patch_rows = _read_json(patch_rows_path)
    if patch_manifest.get("gate") != GREEN_PATCH_GATE:
        blockers.append("patch_manifest_not_green")
    if sha256_file(patch_manifest_path) != str(handoff_manifest.get("patch_manifest_sha256") or ""):
        blockers.append("patch_manifest_sha_mismatch")
    if sha256_file(patch_rows_path) != str(handoff_manifest.get("patch_rows_sha256") or ""):
        blockers.append("patch_rows_sha_mismatch")
    if not isinstance(patch_rows, list):
        blockers.append("patch_rows_not_list")
        patch_rows = []
    if int(handoff_manifest.get("patch_rows_count") or -1) != len(patch_rows):
        blockers.append("handoff_patch_rows_count_mismatch")
    if int(patch_manifest.get("patch_rows_count") or -1) != len(patch_rows):
        blockers.append("patch_manifest_rows_count_mismatch")
    if not patch_rows:
        blockers.append("patch_rows_empty")
    if blockers:
        raise RuntimeError(",".join(blockers))
    expected_approval = approval_phrase_path.read_text(encoding="utf-8").strip()
    return (
        handoff_manifest,
        patch_manifest,
        patch_manifest_path,
        patch_rows,
        approval_phrase_path,
        expected_approval,
    )


def validate_patch_rows_scope(patch_rows: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    seen_keys: set[str] = set()
    for idx, row in enumerate(patch_rows, start=1):
        row_prefix = f"patch_row_{idx}"
        if str(row.get("target_tab") or "") != TARGET_TAB:
            blockers.append(f"{row_prefix}_target_tab_not_allowed")
        if str(row.get("key_column") or "") != KEY_COLUMN:
            blockers.append(f"{row_prefix}_key_column_not_allowed")
        if str(row.get("source_column") or "") != SIZE_COLUMN:
            blockers.append(f"{row_prefix}_source_column_not_allowed")
        key = _clean_key(row.get("key_value"))
        if not key:
            blockers.append(f"{row_prefix}_missing_key_value")
        elif key in seen_keys:
            blockers.append(f"{row_prefix}_duplicate_key_value")
        seen_keys.add(key)
        if not _clean_cell(row.get("planned_cell_value")):
            blockers.append(f"{row_prefix}_missing_planned_cell_value")
    return blockers


def plan_board_cell_updates(
    *,
    contract: OpsBoardContract,
    patch_rows: list[dict[str, Any]],
    board_matrix: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    tab_contract = contract.tabs.get(TARGET_TAB)
    if tab_contract is None:
        return [], [{"blocker": "target_tab_missing_from_contract", "target_tab": TARGET_TAB}]
    if SIZE_COLUMN not in tab_contract.editable_column_set:
        return [], [{"blocker": "my_size_not_editable_by_contract", "target_tab": TARGET_TAB}]
    if KEY_COLUMN not in tab_contract.headers or SIZE_COLUMN not in tab_contract.headers:
        return [], [{"blocker": "required_header_missing_from_contract", "target_tab": TARGET_TAB}]

    scope_blockers = validate_patch_rows_scope(patch_rows)
    for blocker in scope_blockers:
        blockers.append({"blocker": blocker})
    if scope_blockers:
        return [], blockers

    positioned_rows = extract_rows_with_positions_from_matrix(tab_contract.headers, board_matrix)
    by_key: dict[str, dict[str, Any]] = {}
    for positioned in positioned_rows:
        row = dict(positioned.get("row") or {})
        key = _clean_key(row.get(KEY_COLUMN))
        if key:
            by_key[key] = {"sheet_row": int(positioned["sheet_row"]), "row": row}

    size_col_index = tab_contract.headers.index(SIZE_COLUMN) + 1
    size_col_letter = _column_letter(size_col_index)
    for patch_row in patch_rows:
        key = _clean_key(patch_row.get("key_value"))
        planned_value = _clean_cell(patch_row.get("planned_cell_value"))
        positioned = by_key.get(key)
        if positioned is None:
            blockers.append({"blocker": "target_row_missing_from_board", "key_value": key})
            continue
        current_value = _clean_cell((positioned["row"] or {}).get(SIZE_COLUMN))
        if current_value == planned_value:
            continue
        if current_value and current_value != planned_value:
            blockers.append(
                {
                    "blocker": "target_my_size_conflicting_nonblank",
                    "key_value": key,
                    "current_value": current_value,
                    "planned_value": planned_value,
                }
            )
            continue
        sheet_row = int(positioned["sheet_row"])
        updates.append(
            {
                "range": f"{TARGET_TAB}!{size_col_letter}{sheet_row}",
                "tab": TARGET_TAB,
                "column": SIZE_COLUMN,
                "key_column": KEY_COLUMN,
                "key_value": key,
                "sheet_row": sheet_row,
                "value": planned_value,
                "current_value": current_value,
            }
        )

    return updates, blockers


def validate_apply_authority(
    *,
    apply: bool,
    expected_approval: str,
    supplied_approval: str,
    contract_write_env_gate: str,
    environ: dict[str, str] | None = None,
) -> list[str]:
    if not apply:
        return []
    env = environ if environ is not None else os.environ
    blockers: list[str] = []
    if not supplied_approval:
        blockers.append("owner_approval_missing")
    elif supplied_approval.strip() != expected_approval.strip():
        blockers.append("owner_approval_text_mismatch")
    if env.get(contract_write_env_gate) != "1":
        blockers.append(f"{contract_write_env_gate}_not_1")
    if env.get(NARROW_WRITE_ENV_GATE) != "1":
        blockers.append(f"{NARROW_WRITE_ENV_GATE}_not_1")
    return blockers


def _build_client(args: argparse.Namespace, contract: OpsBoardContract) -> GoogleOpsBoardClient:
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    return GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"kaspi_customer_size_google_board_my_size_apply_{stamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-handoff-manifest", type=Path)
    parser.add_argument("--board-matrix-fixture-json", type=Path)
    parser.add_argument("--service-account-json", type=Path)
    parser.add_argument("--spreadsheet-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--owner-approval-text")
    parser.add_argument("--owner-approval-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now().isoformat(timespec="seconds")
    contract = load_ops_board_contract()
    handoff_manifest_path = args.apply_handoff_manifest or _latest_apply_handoff_manifest()
    if handoff_manifest_path is None:
        manifest = {
            "gate": "YELLOW_GOOGLE_BOARD_MY_SIZE_PATCH_BLOCKED_NO_APPLY_HANDOFF",
            "run_at": run_at,
            "blockers": ["apply_handoff_manifest_missing"],
            "google_board_write_performed": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", f"# Google Board MY_SIZE Patch\n\nGate: {manifest['gate']}\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    try:
        (
            handoff_manifest,
            patch_manifest,
            patch_manifest_path,
            patch_rows,
            approval_phrase_path,
            expected_approval,
        ) = load_patch_packet_from_handoff(Path(handoff_manifest_path))
    except RuntimeError as exc:
        blockers = str(exc).split(",") if str(exc) else ["patch_packet_load_failed"]
        manifest = {
            "gate": "YELLOW_GOOGLE_BOARD_MY_SIZE_PATCH_BLOCKED_PACKET_INVALID",
            "run_at": run_at,
            "apply_handoff_manifest_path": str(handoff_manifest_path),
            "blockers": blockers,
            "google_board_write_performed": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", f"# Google Board MY_SIZE Patch\n\nGate: {manifest['gate']}\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    authority_blockers = validate_apply_authority(
        apply=bool(args.apply),
        expected_approval=expected_approval,
        supplied_approval=_read_approval_text(args),
        contract_write_env_gate=contract.write_env_gate,
    )
    if args.apply and args.board_matrix_fixture_json:
        authority_blockers.append("fixture_apply_not_allowed")

    client: GoogleOpsBoardClient | None = None
    live_board_readback = False
    if args.board_matrix_fixture_json:
        board_matrix = _load_matrix_fixture(args.board_matrix_fixture_json)
        board_source = "fixture"
    else:
        try:
            client = _build_client(args, contract)
            board_matrix = client.get_tab_values(TARGET_TAB)
            board_source = "live_google_board"
            live_board_readback = True
        except Exception as exc:
            board_matrix = []
            board_source = "unavailable"
            authority_blockers.append(f"live_board_readback_failed:{type(exc).__name__}")

    if board_source == "unavailable":
        updates = []
        board_blockers: list[dict[str, Any]] = []
    else:
        updates, board_blockers = plan_board_cell_updates(
            contract=contract,
            patch_rows=patch_rows,
            board_matrix=board_matrix,
        )
    blockers = authority_blockers + [str(item.get("blocker") or "unknown_board_blocker") for item in board_blockers]

    already_current_count = max(0, len(patch_rows) - len(updates) - len(board_blockers))
    google_board_write_performed = False
    readback_verified = False
    if args.apply and not blockers:
        if client is None:
            blockers.append("live_google_client_missing")
        elif not updates:
            readback_verified = True
        else:
            with GoogleOpsBoardAutomationLock():
                client.update_cells(updates)
                google_board_write_performed = True
                post_matrix = client.get_tab_values(TARGET_TAB)
            post_apply_updates, post_apply_blockers = plan_board_cell_updates(
                contract=contract,
                patch_rows=patch_rows,
                board_matrix=post_matrix,
            )
            unresolved = [
                item
                for item in post_apply_updates
                if _clean_cell(item.get("current_value")) != _clean_cell(item.get("value"))
            ]
            readback_verified = not post_apply_blockers and not unresolved
            if not readback_verified:
                blockers.append("post_apply_readback_not_verified")

    if blockers:
        gate = (
            "YELLOW_GOOGLE_BOARD_MY_SIZE_PATCH_APPLY_BLOCKED_NO_WRITE"
            if not google_board_write_performed
            else "RED_GOOGLE_BOARD_MY_SIZE_PATCH_APPLY_READBACK_FAILED"
        )
        exit_code = 2
    elif args.apply and not updates:
        gate = "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_ALREADY_CURRENT_NO_WRITE"
        exit_code = 0
    elif args.apply:
        gate = "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_APPLIED_AND_READBACK_VERIFIED"
        exit_code = 0
    else:
        gate = "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_PREFLIGHT_READY_NO_WRITE"
        exit_code = 0

    redacted_updates = [
        {
            "range": item.get("range"),
            "key_column": item.get("key_column"),
            "key_value": item.get("key_value"),
            "column": item.get("column"),
            "planned_value": item.get("value"),
            "current_value_blank": not bool(_clean_cell(item.get("current_value"))),
        }
        for item in updates
    ]
    redacted_updates_json = json.dumps(redacted_updates, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _write_json(output_dir / "planned_cell_updates_redacted.json", redacted_updates)
    _write_json(output_dir / "board_blockers_redacted.json", board_blockers)
    manifest = {
        "gate": gate,
        "run_at": run_at,
        "apply": bool(args.apply),
        "apply_handoff_manifest_path": str(Path(handoff_manifest_path).resolve()),
        "apply_handoff_gate": handoff_manifest.get("gate"),
        "approval_phrase_path": str(approval_phrase_path),
        "patch_manifest_path": str(patch_manifest_path),
        "patch_manifest_gate": patch_manifest.get("gate"),
        "patch_rows_count": len(patch_rows),
        "planned_update_count": len(updates),
        "already_current_count": already_current_count,
        "planned_updates_sha256": hashlib.sha256(redacted_updates_json).hexdigest(),
        "board_source": board_source,
        "live_board_readback": live_board_readback,
        "blockers": blockers,
        "google_board_write_performed": google_board_write_performed,
        "post_apply_readback_verified": readback_verified,
        "db_write_performed": False,
        "kaspi_chat_write_performed": False,
        "telegram_send_performed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Google Board MY_SIZE Patch",
                "",
                f"Gate: {gate}",
                "",
                f"- Apply mode: {bool(args.apply)}",
                f"- Patch rows: {len(patch_rows)}",
                f"- Planned cell updates: {len(updates)}",
                f"- Already current rows: {already_current_count}",
                f"- Board source: {board_source}",
                f"- Google Board write performed: {google_board_write_performed}",
                f"- Post-apply readback verified: {readback_verified}",
                f"- Blockers: {', '.join(blockers) if blockers else 'none'}",
                "",
                "No DB, Kaspi chat, Telegram, waybill, workbook, price, stock, cash, supplier, PO, or scheduler write was performed.",
                "",
            ]
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
