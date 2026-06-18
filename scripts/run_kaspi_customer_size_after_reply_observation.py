#!/usr/bin/env python3
"""Run the local after-reply customer-size staging chain.

This helper starts from a transient reply CSV, records parsed reply facts into
the local customer-size ledger, builds the no-write Google Board MY_SIZE patch
packet, builds the exact owner-approval apply handoff, refreshes workflow
readiness/next-action evidence, and stops.

It never sends customer messages, opens Kaspi, writes Google Board, writes the
production DB, sends Telegram/WhatsApp, or copies raw reply text into evidence.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import sha256_file
from scripts.build_kaspi_customer_size_google_board_apply_handoff import (
    main as google_board_apply_handoff_main,
)
from scripts.build_kaspi_customer_size_google_board_patch_packet import (
    main as google_board_patch_packet_main,
)
from scripts.build_kaspi_customer_size_workflow_readiness_packet import (
    main as workflow_readiness_packet_main,
)
from scripts.record_kaspi_customer_size_reply_observations import (
    main as reply_observations_main,
)
from scripts.report_kaspi_customer_size_next_action import main as next_action_main


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
GREEN_REPLY_GATE = "GREEN_CUSTOMER_SIZE_REPLY_OBSERVATIONS_CLASSIFICATION_READY_NO_EXTERNAL_WRITE"
GREEN_PATCH_GATE = "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"
GREEN_APPLY_HANDOFF_GATE = "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE"
GREEN_GATE = "GREEN_AFTER_REPLY_OBSERVATION_GOOGLE_BOARD_APPLY_HANDOFF_READY_NO_EXTERNAL_WRITE"
YELLOW_GATE = "YELLOW_AFTER_REPLY_OBSERVATION_REVIEW_NEEDED_NO_EXTERNAL_WRITE"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_after_reply_observation_{stamp}"


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


def _stage(stage: str, rc: int, manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    return {
        "stage": stage,
        "return_code": rc,
        "manifest_path": str(manifest_path),
        "gate": manifest.get("gate") or "MISSING",
    }


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size After Reply Observation",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local-only chain after an approved reply-polling observation. This helper does not open Kaspi, send/read customer chats, write Google Board, write production DB, send Telegram/WhatsApp, or change schedulers.",
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
            "## Next Action",
            "",
            f"- {manifest.get('exact_next_action')}",
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
    parser.add_argument("--reply-csv", type=Path, required=True)
    parser.add_argument("--product-type-default", default="CL")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--live-send-approval-manifest", type=Path)
    parser.add_argument("--reply-polling-preflight-manifest", type=Path)
    parser.add_argument("--cadence-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    reply_csv_path = args.reply_csv.resolve()
    db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)

    stages: list[dict[str, Any]] = []
    reply_dir = output_dir / "01_reply_observations"
    reply_rc = reply_observations_main(
        [
            "--ledger-db",
            str(ledger_path),
            "--reply-csv",
            str(reply_csv_path),
            "--product-type-default",
            str(args.product_type_default),
            "--output-dir",
            str(reply_dir),
        ]
    )
    stages.append(_stage("reply_observations", reply_rc, reply_dir / "manifest.json"))

    patch_dir = output_dir / "02_google_board_patch_packet"
    patch_rc = google_board_patch_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            str(args.target_date),
            "--lookback-days",
            str(args.lookback_days),
            "--output-dir",
            str(patch_dir),
        ]
    )
    stages.append(_stage("google_board_patch_packet", patch_rc, patch_dir / "manifest.json"))

    apply_dir = output_dir / "03_google_board_apply_handoff"
    apply_rc = google_board_apply_handoff_main(
        [
            "--patch-manifest",
            str(patch_dir / "manifest.json"),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(apply_dir),
        ]
    )
    stages.append(_stage("google_board_apply_handoff", apply_rc, apply_dir / "manifest.json"))

    readiness_dir = output_dir / "04_workflow_readiness"
    readiness_args = [
        "--db",
        str(db_path),
        "--ledger-db",
        str(ledger_path),
        "--reply-observation-manifest",
        str(reply_dir / "manifest.json"),
        "--google-board-patch-manifest",
        str(patch_dir / "manifest.json"),
        "--output-dir",
        str(readiness_dir),
    ]
    if args.live_send_approval_manifest:
        readiness_args.extend(["--live-send-approval-manifest", str(args.live_send_approval_manifest.resolve())])
    if args.reply_polling_preflight_manifest:
        readiness_args.extend(
            ["--reply-polling-preflight-manifest", str(args.reply_polling_preflight_manifest.resolve())]
        )
    if args.cadence_manifest:
        readiness_args.extend(["--cadence-manifest", str(args.cadence_manifest.resolve())])
    readiness_rc = workflow_readiness_packet_main(readiness_args)
    stages.append(_stage("workflow_readiness", readiness_rc, readiness_dir / "manifest.json"))

    next_action_dir = output_dir / "05_next_action"
    next_action_args = [
        "--google-board-apply-manifest",
        str(apply_dir / "manifest.json"),
        "--output-dir",
        str(next_action_dir),
    ]
    if args.live_send_approval_manifest:
        next_action_args.extend(["--live-send-approval-manifest", str(args.live_send_approval_manifest.resolve())])
    next_action_rc = next_action_main(next_action_args)
    stages.append(_stage("next_action", next_action_rc, next_action_dir / "manifest.json"))

    gates = {stage["stage"]: str(stage.get("gate") or "") for stage in stages}
    blockers: list[str] = []
    if gates.get("reply_observations") != GREEN_REPLY_GATE:
        blockers.append(f"reply_observations_gate={gates.get('reply_observations')}")
    if gates.get("google_board_patch_packet") != GREEN_PATCH_GATE:
        blockers.append(f"google_board_patch_packet_gate={gates.get('google_board_patch_packet')}")
    if gates.get("google_board_apply_handoff") != GREEN_APPLY_HANDOFF_GATE:
        blockers.append(f"google_board_apply_handoff_gate={gates.get('google_board_apply_handoff')}")

    gate = GREEN_GATE if not blockers else YELLOW_GATE
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "reply_csv_path_not_copied_to_evidence": True,
        "reply_csv_sha256": _safe_sha(reply_csv_path),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": _safe_sha(db_path),
        "db_unchanged": db_sha_before == _safe_sha(db_path),
        "ledger_db": str(ledger_path),
        "ledger_sha256_before": ledger_sha_before,
        "ledger_sha256_after": _safe_sha(ledger_path),
        "ledger_mutation_scope": "local_runtime_control_plane_only",
        "stages": stages,
        "reply_observation_manifest_path": str(reply_dir / "manifest.json"),
        "google_board_patch_manifest_path": str(patch_dir / "manifest.json"),
        "google_board_apply_handoff_manifest_path": str(apply_dir / "manifest.json"),
        "workflow_readiness_manifest_path": str(readiness_dir / "manifest.json"),
        "next_action_manifest_path": str(next_action_dir / "manifest.json"),
        "google_board_apply_approval_phrase_path": str(
            apply_dir / "REQUIRED_EXACT_GOOGLE_BOARD_MY_SIZE_APPLY_APPROVAL_PHRASE.txt"
        ),
        "google_board_apply_handoff_path": str(
            apply_dir / "KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF.md"
        ),
        "blockers": blockers,
        "exact_next_action": (
            "Review the Google Board MY_SIZE apply approval phrase; no Board write is authorized until the owner approves it exactly."
            if gate == GREEN_GATE
            else "Inspect the retained blocker before attempting any Google Board apply or waybill/Telegram resume."
        ),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "scheduler_change_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
