#!/usr/bin/env python3
"""Run the local post-canary customer-size workflow sequence.

This is a local evidence/control-plane runner only. It never opens Kaspi,
never sends or reads customer chats, never writes Google Board, never writes the
production DB, and never sends Telegram/WhatsApp. If the one-order live-send
canary result is not already GREEN, it stops before any ledger transition.

When the live-send result is GREEN, the runner:

- records the local runtime ledger transition to REQUEST_SENT;
- builds the reply-polling handoff;
- builds the approval-gated reply-polling preflight;
- refreshes the Google Board patch/apply handoff packets;
- rebuilds workflow readiness and next-action evidence.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from core.ops.customer_size_request import sha256_file
from scripts.build_kaspi_customer_size_google_board_apply_handoff import (
    main as google_board_apply_handoff_main,
)
from scripts.build_kaspi_customer_size_google_board_patch_packet import (
    main as google_board_patch_packet_main,
)
from scripts.build_kaspi_customer_size_reply_polling_handoff import (
    main as reply_polling_handoff_main,
)
from scripts.build_kaspi_customer_size_workflow_readiness_packet import (
    main as workflow_readiness_packet_main,
)
from scripts.preflight_kaspi_customer_size_reply_polling_execution import (
    GREEN_GATE as REPLY_POLLING_PREFLIGHT_GREEN_GATE,
    YELLOW_AWAITING_APPROVAL_GATE as REPLY_POLLING_AWAITING_APPROVAL_GATE,
    main as reply_polling_preflight_main,
)
from scripts.record_kaspi_customer_size_live_send_canary_acceptance import (
    main as record_live_send_canary_acceptance_main,
)
from scripts.report_kaspi_customer_size_next_action import main as next_action_report_main


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
GREEN_ACCEPTANCE_GATE = (
    "GREEN_LIVE_SEND_CANARY_ACCEPTANCE_RECORDED_REPLY_POLL_READY_NO_EXTERNAL_WRITE"
)
LIVE_SEND_EXECUTION_PREFLIGHT_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
PREFLIGHT_ALIGNMENT_BLOCKED_GATE = (
    "YELLOW_POST_CANARY_SEQUENCE_BLOCKED_LIVE_SEND_PREFLIGHT_ALIGNMENT_NO_EXTERNAL_WRITE"
)
BLOCKED_GATE = "YELLOW_POST_CANARY_SEQUENCE_BLOCKED_LIVE_SEND_RESULT_NOT_GREEN_NO_EXTERNAL_WRITE"
GREEN_SEQUENCE_GATE = "GREEN_POST_CANARY_SEQUENCE_LOCAL_REPLY_POLLING_READY_NO_EXTERNAL_WRITE"
YELLOW_SEQUENCE_GATE = "YELLOW_POST_CANARY_SEQUENCE_LOCAL_FOLLOWUP_REVIEW_NEEDED_NO_EXTERNAL_WRITE"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_post_canary_sequence_{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _approval_manifest_path(approval_dir: Path) -> Path:
    return approval_dir / "manifest.json"


def _approval_phrase_path(approval_dir: Path) -> Path:
    return approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"


def _live_send_execution_handoff_path(approval_dir: Path) -> Path:
    return (
        approval_dir
        / "live_send_execution_handoff"
        / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    )


def _stage_record(stage: str, rc: int, manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    return {
        "stage": stage,
        "return_code": rc,
        "manifest_path": str(manifest_path),
        "gate": manifest.get("gate") or "MISSING",
    }


def _target_alignment_fields(payload: dict[str, Any]) -> dict[str, str]:
    fields = (
        "selected_order_ref",
        "selected_db_row_id",
        "selected_store_code",
        "template_hash",
        "expected_merchant_account_id",
    )
    return {field: str(payload.get(field) or "") for field in fields}


def _live_send_preflight_alignment(
    *,
    approval_manifest: dict[str, Any],
    preflight_path: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    """Validate the live-send preflight used by the post-canary chain.

    The post-canary runner can mutate the local request ledger after a GREEN
    live-send result. When supplied, this guard proves the target approved for
    send is the same target that had a GREEN execution preflight.
    """
    if preflight_path is None:
        return {}, []
    resolved_path = preflight_path.resolve()
    if not resolved_path.exists():
        return {
            "path": str(resolved_path),
            "exists": False,
            "gate": "MISSING",
        }, ["live_send_execution_preflight_manifest_missing"]

    preflight_manifest = _read_json(resolved_path)
    blockers: list[str] = []
    gate = str(preflight_manifest.get("gate") or "")
    if gate != LIVE_SEND_EXECUTION_PREFLIGHT_GREEN_GATE:
        blockers.append(f"live_send_execution_preflight_not_green:{gate or 'MISSING'}")

    approval_fields = _target_alignment_fields(approval_manifest)
    preflight_fields = _target_alignment_fields(preflight_manifest)
    for field, approval_value in approval_fields.items():
        preflight_value = preflight_fields.get(field, "")
        if approval_value and preflight_value and approval_value != preflight_value:
            blockers.append(f"approval_preflight_target_mismatch:{field}")
        elif approval_value and not preflight_value:
            blockers.append(f"live_send_execution_preflight_missing_field:{field}")
        elif preflight_value and not approval_value:
            blockers.append(f"approval_manifest_missing_field:{field}")

    return {
        "path": str(resolved_path),
        "exists": True,
        "gate": gate,
        "sha256": _safe_sha(resolved_path),
        "approval_target_fields": approval_fields,
        "preflight_target_fields": preflight_fields,
    }, blockers


def _run_stage(
    stage: str,
    func: Callable[[list[str]], int],
    argv: list[str],
    manifest_path: Path,
) -> dict[str, Any]:
    rc = func(argv)
    return _stage_record(stage, rc, manifest_path)


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size Post-Canary Sequence",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local-only orchestration after the one-order live-send canary. This runner does not open Kaspi, send/read customer messages, write Google Board, write production DB, send Telegram/WhatsApp, or change schedulers.",
        "",
        "## Stages",
        "",
    ]
    for stage in manifest.get("stages") or []:
        lines.append(
            f"- `{stage['stage']}`: `{stage.get('gate')}` rc={stage.get('return_code')} manifest=`{stage.get('manifest_path')}`"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- {manifest.get('exact_next_action')}",
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Google Board write allowed: false",
            "- Production DB write allowed: false",
            "- Telegram/WhatsApp send allowed: false",
            "- Raw order IDs exported: false",
            "- Raw reply text exported: false",
            "",
        ]
    )
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--resident-session-reuse-manifest", type=Path)
    parser.add_argument(
        "--live-send-execution-preflight-manifest",
        type=Path,
        help=(
            "Optional GREEN no-send execution-preflight manifest that must match "
            "the approval packet before the local post-canary ledger transition."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--reply-poll-window-minutes",
        action="append",
        help="Comma-separated or repeated positive minute offsets for the acceptance bridge.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    approval_dir = args.approval_dir.resolve()
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)
    approval_manifest_path = _approval_manifest_path(approval_dir)
    approval_manifest = _read_json(approval_manifest_path) if approval_manifest_path.exists() else {}
    live_send_preflight, live_send_preflight_blockers = _live_send_preflight_alignment(
        approval_manifest=approval_manifest,
        preflight_path=args.live_send_execution_preflight_manifest,
    )

    if live_send_preflight_blockers:
        manifest = {
            "gate": PREFLIGHT_ALIGNMENT_BLOCKED_GATE,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "approval_dir": str(approval_dir),
            "approval_manifest_path": str(approval_manifest_path),
            "approval_manifest_sha256": _safe_sha(approval_manifest_path),
            "approval_phrase_path": str(_approval_phrase_path(approval_dir)),
            "live_send_execution_handoff_path": str(_live_send_execution_handoff_path(approval_dir)),
            "live_send_execution_preflight_manifest": live_send_preflight,
            "db_path": str(db_path),
            "db_sha256_before": db_sha_before,
            "db_sha256_after": _safe_sha(db_path),
            "db_unchanged": db_sha_before == _safe_sha(db_path),
            "ledger_db": str(ledger_path),
            "ledger_sha256_before": ledger_sha_before,
            "ledger_sha256_after": _safe_sha(ledger_path),
            "ledger_updated": False,
            "stages": [],
            "blockers": live_send_preflight_blockers,
            "exact_next_action": "Rerun post-canary only with the GREEN live-send execution preflight manifest that matches the approval packet and sent result.",
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", _closeout(manifest))
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    stages: list[dict[str, Any]] = []
    acceptance_dir = output_dir / "01_live_send_acceptance"
    acceptance_args = [
        "--approval-dir",
        str(approval_dir),
        "--ledger-db",
        str(ledger_path),
        "--output-dir",
        str(acceptance_dir),
    ]
    for value in args.reply_poll_window_minutes or []:
        acceptance_args.extend(["--reply-poll-window-minutes", str(value)])
    stages.append(
        _run_stage(
            "live_send_acceptance_bridge",
            record_live_send_canary_acceptance_main,
            acceptance_args,
            acceptance_dir / "manifest.json",
        )
    )
    acceptance_gate = str(stages[-1].get("gate") or "")

    if acceptance_gate != GREEN_ACCEPTANCE_GATE:
        manifest = {
            "gate": BLOCKED_GATE,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "approval_dir": str(approval_dir),
            "approval_manifest_path": str(_approval_manifest_path(approval_dir)),
            "approval_manifest_sha256": _safe_sha(_approval_manifest_path(approval_dir)),
            "approval_phrase_path": str(_approval_phrase_path(approval_dir)),
            "live_send_execution_handoff_path": str(_live_send_execution_handoff_path(approval_dir)),
            "live_send_execution_preflight_manifest": live_send_preflight,
            "db_path": str(db_path),
            "db_sha256_before": db_sha_before,
            "db_sha256_after": _safe_sha(db_path),
            "db_unchanged": db_sha_before == _safe_sha(db_path),
            "ledger_db": str(ledger_path),
            "ledger_sha256_before": ledger_sha_before,
            "ledger_sha256_after": _safe_sha(ledger_path),
            "ledger_updated": False,
            "stages": stages,
            "blockers": [f"live_send_acceptance_gate={acceptance_gate}"],
            "exact_next_action": "Execute the owner-approved one-order live-send canary first, then rerun this post-canary sequence.",
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", _closeout(manifest))
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    reply_handoff_dir = output_dir / "02_reply_polling_handoff"
    stages.append(
        _run_stage(
            "reply_polling_handoff",
            reply_polling_handoff_main,
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--output-dir",
                str(reply_handoff_dir),
            ],
            reply_handoff_dir / "manifest.json",
        )
    )

    reply_preflight_dir = output_dir / "03_reply_polling_preflight"
    reply_preflight_args = [
        "--ledger-db",
        str(ledger_path),
        "--output-dir",
        str(reply_preflight_dir),
    ]
    if args.resident_session_reuse_manifest:
        reply_preflight_args.extend(
            ["--resident-session-reuse-manifest", str(args.resident_session_reuse_manifest.resolve())]
        )
    stages.append(
        _run_stage(
            "reply_polling_execution_preflight",
            reply_polling_preflight_main,
            reply_preflight_args,
            reply_preflight_dir / "manifest.json",
        )
    )

    patch_dir = output_dir / "04_google_board_patch_packet"
    stages.append(
        _run_stage(
            "google_board_patch_packet",
            google_board_patch_packet_main,
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                args.target_date,
                "--lookback-days",
                str(args.lookback_days),
                "--output-dir",
                str(patch_dir),
            ],
            patch_dir / "manifest.json",
        )
    )

    apply_handoff_dir = output_dir / "05_google_board_apply_handoff"
    stages.append(
        _run_stage(
            "google_board_apply_handoff",
            google_board_apply_handoff_main,
            [
                "--patch-manifest",
                str(patch_dir / "manifest.json"),
                "--ledger-db",
                str(ledger_path),
                "--output-dir",
                str(apply_handoff_dir),
            ],
            apply_handoff_dir / "manifest.json",
        )
    )

    readiness_dir = output_dir / "06_workflow_readiness"
    stages.append(
        _run_stage(
            "workflow_readiness",
            workflow_readiness_packet_main,
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--live-send-approval-manifest",
                str(_approval_manifest_path(approval_dir)),
                "--reply-polling-preflight-manifest",
                str(reply_preflight_dir / "manifest.json"),
                "--google-board-patch-manifest",
                str(patch_dir / "manifest.json"),
                "--output-dir",
                str(readiness_dir),
            ],
            readiness_dir / "manifest.json",
        )
    )

    next_action_dir = output_dir / "07_next_action"
    stages.append(
        _run_stage(
            "next_action_report",
            next_action_report_main,
            [
                "--live-send-approval-manifest",
                str(_approval_manifest_path(approval_dir)),
                "--reply-polling-manifest",
                str(reply_handoff_dir / "manifest.json"),
                "--google-board-apply-manifest",
                str(apply_handoff_dir / "manifest.json"),
                "--output-dir",
                str(next_action_dir),
            ],
            next_action_dir / "manifest.json",
        )
    )

    reply_preflight_gate = str(stages[2].get("gate") or "")
    all_stage_gates = [str(stage.get("gate") or "") for stage in stages]
    unsafe = [gate for gate in all_stage_gates if gate.startswith("RED_")]
    if unsafe:
        gate = YELLOW_SEQUENCE_GATE
        blockers = [f"unsafe_stage_gate={gate_value}" for gate_value in unsafe]
        exact_next_action = "Stop and inspect the RED stage before any follow-up."
    elif reply_preflight_gate in {REPLY_POLLING_AWAITING_APPROVAL_GATE, REPLY_POLLING_PREFLIGHT_GREEN_GATE}:
        gate = GREEN_SEQUENCE_GATE
        blockers = []
        exact_next_action = "Review the generated reply-polling approval phrase; no chat read is authorized until the owner approves it exactly."
    else:
        gate = YELLOW_SEQUENCE_GATE
        blockers = [f"reply_polling_preflight_gate={reply_preflight_gate}"]
        exact_next_action = "Inspect the reply-polling preflight blocker before attempting any chat read."

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "approval_manifest_path": str(_approval_manifest_path(approval_dir)),
        "approval_manifest_sha256": _safe_sha(_approval_manifest_path(approval_dir)),
        "live_send_execution_preflight_manifest": live_send_preflight,
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": _safe_sha(db_path),
        "db_unchanged": db_sha_before == _safe_sha(db_path),
        "ledger_db": str(ledger_path),
        "ledger_sha256_before": ledger_sha_before,
        "ledger_sha256_after": _safe_sha(ledger_path),
        "ledger_updated": ledger_sha_before != _safe_sha(ledger_path),
        "stages": stages,
        "reply_polling_handoff_path": str(reply_handoff_dir / "KASPI_CUSTOMER_SIZE_REPLY_POLLING_HANDOFF.md"),
        "reply_polling_approval_phrase_path": str(
            reply_preflight_dir / "REQUIRED_EXACT_REPLY_POLLING_APPROVAL_PHRASE.txt"
        ),
        "google_board_patch_manifest_path": str(patch_dir / "manifest.json"),
        "google_board_apply_handoff_path": str(
            apply_handoff_dir / "KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF.md"
        ),
        "workflow_readiness_manifest_path": str(readiness_dir / "manifest.json"),
        "next_action_manifest_path": str(next_action_dir / "manifest.json"),
        "blockers": blockers,
        "exact_next_action": exact_next_action,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate == GREEN_SEQUENCE_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
