#!/usr/bin/env python3
"""Post-bridge watcher for the Kaspi open-chat/no-type canary.

This is a local no-send coordinator. It validates the open-chat/no-type result
when present, rebuilds workflow readiness with that validation, and refreshes
the owner dashboard so the next gate is explicit.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.build_kaspi_customer_size_owner_dashboard import main as owner_dashboard_main
from scripts.build_kaspi_customer_size_workflow_readiness_packet import (
    main as workflow_readiness_main,
)
from scripts.report_kaspi_customer_size_post_open_chat_readiness import (
    GREEN_GATE as POST_OPEN_GREEN_GATE,
    RED_GATE as POST_OPEN_RED_GATE,
    build_report as post_open_build_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_READY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_BRIDGE_READY_NO_ACTION"
BRIDGE_APPLY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_BRIDGE_COMMAND_ENQUEUED_NO_SEND"
GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_AFTER_BRIDGE_WATCH_READY_FOR_NEXT_GATE_NO_EXTERNAL_WRITE"
YELLOW_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_AFTER_BRIDGE_WATCH_BLOCKED_NO_EXTERNAL_WRITE"
RED_GATE = "RED_OPEN_CHAT_NO_TYPE_AFTER_BRIDGE_WATCH_UNSAFE_NO_EXTERNAL_WRITE"


def _latest(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


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


def _path_from_text(text: Any) -> Path | None:
    value = str(text or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _path_arg(path: Path | None) -> list[str]:
    return [str(path)] if path else []


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_open_no_type_after_bridge_watch_{stamp}"


def _source_paths_from_workflow(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    data = _read_json(path)
    return dict(data.get("source_manifests") or {})


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Open-Chat No-Type After-Bridge Watch",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local-only coordinator after the open-chat/no-type bridge. It validates",
        "result evidence and refreshes readiness/dashboard artifacts. It does not",
        "open Kaspi, type, send, write Google Board, write DB, or send Telegram/WhatsApp.",
        "",
        "## Inputs",
        "",
        f"- Bridge manifest: `{manifest.get('bridge_manifest_path')}`",
        f"- Source workflow manifest: `{manifest.get('source_workflow_manifest_path')}`",
        "",
        "## Outputs",
        "",
        f"- Post-open readiness: `{manifest.get('post_open_readiness_manifest_path')}`",
        f"- Workflow readiness: `{manifest.get('workflow_readiness_manifest_path')}`",
        f"- Owner dashboard: `{manifest.get('owner_dashboard_manifest_path')}`",
        "",
        "## Gates",
        "",
        f"- Bridge gate: `{manifest.get('bridge_gate')}`",
        f"- Post-open gate: `{manifest.get('post_open_gate')}`",
        f"- Workflow gate: `{manifest.get('workflow_gate')}`",
        f"- Dashboard gate: `{manifest.get('owner_dashboard_gate')}`",
        "",
        "## Safety",
        "",
        "- Customer send performed: false",
        "- Kaspi chat write performed: false",
        "- Browser action performed by watch: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Google Board write allowed: false",
        "- Production DB write allowed: false",
        "- Telegram/WhatsApp send allowed: false",
        "",
        "## Next Action",
        "",
        f"- {manifest.get('exact_next_action')}",
        "",
    ]
    blockers = [*(manifest.get("unsafe_blockers") or []), *(manifest.get("blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-manifest", type=Path)
    parser.add_argument("--source-workflow-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--live-send-approval-manifest", type=Path)
    parser.add_argument("--live-send-preflight-manifest", type=Path)
    parser.add_argument("--resident-heartbeat-manifest", type=Path)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []
    unsafe: list[str] = []

    bridge_path = args.bridge_manifest or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_bridge_*/manifest.json"
    )
    source_workflow_path = args.source_workflow_manifest or _latest(
        "exports/validation/kaspi_customer_size_workflow_readiness_*/manifest.json"
    )
    bridge_path = bridge_path.resolve() if bridge_path else None
    source_workflow_path = source_workflow_path.resolve() if source_workflow_path else None
    bridge: dict[str, Any] = {}
    if not bridge_path or not bridge_path.exists():
        blockers.append("bridge_manifest_missing")
    else:
        bridge = _read_json(bridge_path)
        if bridge.get("gate") not in {BRIDGE_READY_GATE, BRIDGE_APPLY_GATE}:
            blockers.append(f"bridge_gate_not_ready:{bridge.get('gate') or 'MISSING'}")
        if bridge.get("message_sent") is not False:
            unsafe.append("bridge_message_sent_not_false")
        if bridge.get("message_text_typed") is not False:
            unsafe.append("bridge_message_text_typed_not_false")

    source_paths = _source_paths_from_workflow(source_workflow_path)
    open_chat_packet_dir = _path_from_text(bridge.get("approval_phrase_path"))
    if open_chat_packet_dir:
        open_chat_packet_dir = open_chat_packet_dir.parent
    else:
        blockers.append("open_chat_packet_dir_unresolved_from_bridge")

    post_open_dir = output_dir / "01_post_open_chat_readiness"
    post_open_args = argparse.Namespace(
        open_chat_packet_dir=open_chat_packet_dir or (output_dir / "missing_packet"),
        open_chat_validation_json=None,
        live_send_approval_manifest=(
            args.live_send_approval_manifest
            or _path_from_text(source_paths.get("live_send_approval_manifest"))
            or (output_dir / "missing_live_send_approval.json")
        ),
        live_send_preflight_manifest=(
            args.live_send_preflight_manifest
            or _path_from_text(source_paths.get("live_send_execution_preflight_manifest"))
            or (output_dir / "missing_live_send_preflight.json")
        ),
        resident_current_heartbeat=(
            args.resident_heartbeat_manifest
            or _path_from_text(bridge.get("heartbeat_path"))
            or _path_from_text(source_paths.get("resident_heartbeat_manifest"))
            or (output_dir / "missing_heartbeat.json")
        ),
        output_dir=post_open_dir,
    )
    post_open = post_open_build_report(post_open_args)

    workflow_dir = output_dir / "02_workflow_readiness"
    workflow_args = [
        "--open-chat-no-type-result-validation-json",
        str(post_open_dir / "open_chat_no_type_result_validation.json"),
        "--output-dir",
        str(workflow_dir),
    ]
    source_arg_map = {
        "--resident-heartbeat-manifest": "resident_heartbeat_manifest",
        "--live-ui-validation-json": "live_ui_validation_json",
        "--resident-button-manifest": "resident_button_manifest",
        "--chrome-reconnect-manifest": "chrome_reconnect_manifest",
        "--live-send-approval-manifest": "live_send_approval_manifest",
        "--open-chat-no-type-packet-manifest": "open_chat_no_type_packet_manifest",
        "--live-send-execution-preflight-manifest": "live_send_execution_preflight_manifest",
        "--after-live-send-watch-manifest": "after_live_send_watch_manifest",
        "--reply-polling-preflight-manifest": "reply_polling_preflight_manifest",
        "--reply-observation-manifest": "reply_observation_manifest",
        "--google-board-patch-manifest": "google_board_patch_manifest",
        "--google-board-apply-manifest": "google_board_apply_manifest",
        "--after-board-apply-readiness-manifest": "after_board_apply_readiness_manifest",
        "--cadence-manifest": "cadence_manifest",
    }
    for flag, key in source_arg_map.items():
        path = _path_from_text(source_paths.get(key))
        if path:
            workflow_args.extend([flag, str(path)])
    workflow_rc = workflow_readiness_main(workflow_args)
    workflow_manifest = _read_json(workflow_dir / "manifest.json")

    dashboard_dir = output_dir / "03_owner_dashboard"
    dashboard_args = ["--workflow-dir", str(workflow_dir), "--output-dir", str(dashboard_dir)]
    live_send_approval_manifest = _path_from_text(source_paths.get("live_send_approval_manifest"))
    if live_send_approval_manifest:
        dashboard_args.extend(["--live-send-approval-dir", str(live_send_approval_manifest.parent)])
    dashboard_rc = owner_dashboard_main(dashboard_args)
    dashboard_manifest = _read_json(dashboard_dir / "manifest.json")

    post_open_gate = str(post_open.get("gate") or "MISSING")
    workflow_gate = str(workflow_manifest.get("gate") or "MISSING")
    dashboard_gate = str(dashboard_manifest.get("gate") or "MISSING")
    if post_open_gate.startswith("RED_"):
        unsafe.append(f"post_open_gate_red:{post_open_gate}")
    elif post_open_gate != POST_OPEN_GREEN_GATE:
        blockers.append(f"post_open_gate_not_green:{post_open_gate}")
    if workflow_rc not in {0, 1}:
        unsafe.append(f"workflow_readiness_unexpected_rc:{workflow_rc}")
    if dashboard_rc != 0:
        unsafe.append(f"owner_dashboard_unexpected_rc:{dashboard_rc}")

    if unsafe:
        gate = RED_GATE
        exact_next_action = "Stop and inspect unsafe blockers before any live send or further chat action."
    elif blockers:
        gate = YELLOW_GATE
        exact_next_action = (
            "Complete the open-chat/no-type canary result first; do not type, send, "
            "or run the live-send canary yet."
        )
    else:
        gate = GREEN_GATE
        exact_next_action = (
            "Review the refreshed dashboard and proceed only to the separately owner-approved "
            "one-order live-send canary for the same target."
        )

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "bridge_manifest_path": str(bridge_path) if bridge_path else "",
        "bridge_gate": bridge.get("gate", ""),
        "source_workflow_manifest_path": str(source_workflow_path) if source_workflow_path else "",
        "post_open_readiness_manifest_path": str(post_open_dir / "manifest.json"),
        "post_open_gate": post_open_gate,
        "workflow_readiness_manifest_path": str(workflow_dir / "manifest.json"),
        "workflow_gate": workflow_gate,
        "owner_dashboard_manifest_path": str(dashboard_dir / "manifest.json"),
        "owner_dashboard_gate": dashboard_gate,
        "exact_next_action": exact_next_action,
        "blockers": sorted(set(blockers)),
        "unsafe_blockers": sorted(set(unsafe)),
        "customer_send_performed": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_performed": False,
        "browser_action_performed": False,
        "message_text_typed": False,
        "message_sent": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_closeout(manifest), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = run(args)
    if str(manifest.get("gate") or "").startswith("RED_"):
        return 2
    return 0 if manifest.get("gate") == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
