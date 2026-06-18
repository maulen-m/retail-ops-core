#!/usr/bin/env python3
"""Build a decision matrix for Kaspi customer-size automation transport options."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYNTHESIS = (
    Path.home()
    / "Docs"
    / "Autonomous_business_agent_handoffs"
    / "2026-06-17_kaspi_customer_size_indirect_api_research"
    / "independent_researcher_orchestrator_report__LIVE_CONFIRMED_20260617.md"
)
FALLBACK_SYNTHESIS = (
    Path.home()
    / "Docs"
    / "Autonomous_business_agent_handoffs"
    / "2026-06-15_kaspi_customer_size_message_automation_research"
    / "orchestrator_synthesis_closeout.md"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _latest_workflow_dir() -> Path:
    matches = [
        path
        for path in (REPO_ROOT / "exports" / "validation").glob(
            "kaspi_customer_size_workflow_readiness_*"
        )
        if (path / "manifest.json").exists()
    ]
    if not matches:
        raise FileNotFoundError("No kaspi_customer_size_workflow_readiness_* packet found")
    return max(matches, key=lambda path: (path / "manifest.json").stat().st_mtime)


def _default_output_dir(workflow_dir: Path) -> Path:
    return workflow_dir / "automation_options_matrix"


def _stage_gate(stages: list[dict[str, Any]], stage: str) -> str:
    for row in stages:
        if row.get("stage") == stage:
            return str(row.get("gate") or "MISSING")
    return "MISSING"


def _has_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def _live_chat_api_surface_confirmed(synthesis_text: str) -> bool:
    text = synthesis_text.lower()
    return (
        "mc.shop.kaspi.kz/chats/api/mobile/api/v1" in text
        and "group/getdiffgroups/chat" in text
    )


def build_matrix(
    *,
    workflow_manifest: dict[str, Any],
    workflow_stages: list[dict[str, Any]],
    synthesis_text: str,
) -> list[dict[str, Any]]:
    ledger = workflow_manifest.get("ledger_summary") or {}
    detection_ready = int(ledger.get("ledger_rows") or 0) > 0
    live_ui_gate = _stage_gate(workflow_stages, "live_ui_no_send_proof")
    chrome_gate = _stage_gate(workflow_stages, "chrome_or_computer_use_access")
    board_gate = _stage_gate(workflow_stages, "google_board_my_size_patch_packet")
    chrome_retry_failed = "UNAVAILABLE_AFTER_APPROVED_RETRY" in chrome_gate
    ui_next_step = (
        "use helper agent with working Computer Use/Chrome control to record no-send visual proof"
        if chrome_retry_failed
        else "approve Chrome Profile 4 reconnect, then prove merchant/order/chat button without typing or sending"
    )
    chrome_next_step = (
        "reinstall/repair Codex Chrome plugin or switch to Computer Use helper; do not retry via other browser controllers"
        if chrome_retry_failed
        else "open selected Profile 4 window after exact owner approval and retry extension bridge"
    )
    live_chat_surface_confirmed = _live_chat_api_surface_confirmed(synthesis_text)
    direct_api_status = (
        "LIVE_SURFACE_CONFIRMED_SEND_UNPROVEN"
        if live_chat_surface_confirmed
        else (
            "PROMISING_BUT_UNPROVEN"
            if _has_phrase(synthesis_text, "sendMessage")
            else "NOT_PROVEN"
        )
    )
    direct_api_next_step = (
        "run the guarded no-send metadata capture against mc.shop.kaspi.kz/chats/api/mobile/api/v1; block send/read-status routes and do not replay"
        if live_chat_surface_confirmed
        else "only after UI no-send proof, capture endpoint shape without secrets on a safe canary path"
    )

    return [
        {
            "rank": 1,
            "option": "official_kaspi_order_api_for_detection",
            "recommended_role": "primary_order_detection_queue",
            "current_status": "READY_FOR_DETECTION" if detection_ready else "NOT_READY",
            "evidence_gate": "GREEN_LEDGER_HAS_ROWS" if detection_ready else "YELLOW_LEDGER_EMPTY",
            "what_it_can_do": "detect active missing-size orders early from API/DB sync",
            "what_it_cannot_do_yet": "send or read customer chat messages",
            "next_step": "keep using scheduler preflight/cadence to refresh local ledger",
            "customer_send_allowed": False,
        },
        {
            "rank": 2,
            "option": "kaspi_merchant_ui_browser_automation",
            "recommended_role": "first_message_transport_candidate",
            "current_status": (
                "BLOCKED_ON_COMPUTER_USE_OR_PLUGIN_REPAIR"
                if chrome_retry_failed
                else "BLOCKED_ON_NO_SEND_PROOF"
            ),
            "evidence_gate": live_ui_gate,
            "what_it_can_do": "likely search order and expose customer chat button in logged-in merchant UI",
            "what_it_cannot_do_yet": "send batch messages; current no-send proof is not green",
            "next_step": ui_next_step,
            "customer_send_allowed": False,
        },
        {
            "rank": 3,
            "option": "hardened_no_send_chat_metadata_capture",
            "recommended_role": "safe_api_surface_discovery_before_any_hidden_send",
            "current_status": (
                "READY_TO_RUN_NO_SEND_WITH_OWNER_LOGGED_IN_PROFILE"
                if live_chat_surface_confirmed
                else "READY_BUT_STATIC_ONLY_TARGETS_NEED_RECHECK"
            ),
            "evidence_gate": (
                "GREEN_LIVE_CHAT_API_BASE_CONFIRMED_NO_SEND"
                if live_chat_surface_confirmed
                else "YELLOW_STATIC_ROUTE_MAP_ONLY"
            ),
            "what_it_can_do": "capture sanitized method/path/status/header-name shapes while hard-blocking sendMessage, typing/sendText, startChat, and messageStatus/changeStatus",
            "what_it_cannot_do_yet": "prove safe sending or authorize direct replay",
            "next_step": direct_api_next_step,
            "customer_send_allowed": False,
        },
        {
            "rank": 4,
            "option": "direct_kaspi_chat_network_api",
            "recommended_role": "future_possible_transport_after_canary",
            "current_status": direct_api_status,
            "evidence_gate": "YELLOW_DIRECT_CHAT_API_SEND_BLOCKED_UNTIL_PAYLOAD_CSRF_IDEMPOTENCY_AND_SIDE_EFFECT_CANARY",
            "what_it_can_do": "may eventually reduce UI friction if endpoint payload/session/read-status behavior is proven",
            "what_it_cannot_do_yet": "cannot be used safely without payload, CSRF/session, duplicate-send, and read-status proof",
            "next_step": direct_api_next_step,
            "customer_send_allowed": False,
        },
        {
            "rank": 5,
            "option": "chrome_profile_session_reuse",
            "recommended_role": "preferred_login_persistence_method",
            "current_status": (
                "EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"
                if chrome_retry_failed
                else "APPROVAL_GATED_RECONNECT"
            ),
            "evidence_gate": chrome_gate,
            "what_it_can_do": "reuse owner-open logged-in Chrome profile without exporting cookies or tokens",
            "what_it_cannot_do_yet": "guarantee long-term session stability or bypass Kaspi reauth",
            "next_step": chrome_next_step,
            "customer_send_allowed": False,
        },
        {
            "rank": 6,
            "option": "macos_sms_imessage_otp_assist",
            "recommended_role": "human_in_the_loop_login_recovery_only",
            "current_status": "PRIVACY_REVIEW_REQUIRED",
            "evidence_gate": "YELLOW_SMS_OTP_AUTOMATION_NOT_RECOMMENDED_YET",
            "what_it_can_do": "could theoretically help owner relay OTP in a future strict Shortcuts-style prototype",
            "what_it_cannot_do_yet": "should not read Messages DB or private SMS corpus in this lane",
            "next_step": "keep OTP manual unless owner approves a separate privacy-reviewed OTP relay prototype",
            "customer_send_allowed": False,
        },
        {
            "rank": 7,
            "option": "reply_observation_to_size_classification",
            "recommended_role": "primary_reply_processing_path_after_send",
            "current_status": "READY_NO_EXTERNAL_WRITE",
            "evidence_gate": "READY_FOR_FUTURE_REPLY_OBSERVATION_NO_EXTERNAL_WRITE",
            "what_it_can_do": "parse transient reply text into height/weight/explicit size and dry-run MY_SIZE patch rows",
            "what_it_cannot_do_yet": "automatically fetch replies from Kaspi chat; customer send has not happened yet",
            "next_step": "after approved send, use transient CSV or future chat poller to record redacted reply facts",
            "customer_send_allowed": False,
        },
        {
            "rank": 8,
            "option": "google_board_my_size_writeback",
            "recommended_role": "operator_approved_size_truth_bridge",
            "current_status": "PATCH_PACKET_READY_NO_WRITE" if board_gate.startswith("GREEN") else "WAITING",
            "evidence_gate": board_gate,
            "what_it_can_do": "prepare SalesRaw_Today.MY_SIZE patch rows and existing DB writeback gate",
            "what_it_cannot_do_yet": "write Google Board or DB without separate owner/apply approval",
            "next_step": "review one ready patch row, then use existing writeback gate when approved",
            "customer_send_allowed": False,
        },
        {
            "rank": 9,
            "option": "telegram_waybill_resume",
            "recommended_role": "final_shipping_closeout_after_sizes",
            "current_status": "BLOCKED_UNTIL_SIZE_GATE_GREEN",
            "evidence_gate": "BLOCKED_UNTIL_NO_BLANK_MY_SIZE_AND_GOOGLE_BOARD_READY",
            "what_it_can_do": "resume existing PDF bundle/Telegram path after sizes are present",
            "what_it_cannot_do_yet": "ship size-missing orders before MY_SIZE gate is complete",
            "next_step": "resume only after Google Board and DB size writeback are green",
            "customer_send_allowed": False,
        },
    ]


def _build_markdown(rows: list[dict[str, Any]], *, workflow_dir: Path, synthesis_path: Path) -> str:
    lines = [
        "# Kaspi Customer Size Automation Options Matrix",
        "",
        "Gate: GREEN_AUTOMATION_OPTIONS_MATRIX_BUILT_FROM_REDACTED_EVIDENCE",
        "",
        f"- Workflow evidence: {workflow_dir}",
        f"- Research synthesis: {synthesis_path}",
        "",
        "| Rank | Option | Current Status | Role | Evidence Gate | Next Step |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {rank} | {option} | {status} | {role} | {gate} | {next_step} |".format(
                rank=row["rank"],
                option=row["option"],
                status=row["current_status"],
                role=row["recommended_role"],
                gate=row["evidence_gate"],
                next_step=row["next_step"],
            )
        )
    lines.extend(
        [
            "",
            "## Bottom Line",
            "",
            "- Best immediate path: "
            + (
                "Computer Use/helper visual proof -> one-order owner-approved send canary."
                if any(
                    row["option"] == "chrome_profile_session_reuse"
                    and row["current_status"] == "EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"
                    for row in rows
                )
                else "Chrome/Profile 4 reconnect -> live UI no-send proof -> one-order owner-approved send canary."
            ),
            "- Best long-term path if proven later: direct Kaspi chat API, but only after payload/session/read-status/duplicate-send canary evidence.",
            "- Do not use Messages DB scraping or cookie/session export in the current lane.",
            "- Google Board and Telegram remain downstream gates, not message-transport solutions.",
            "",
            "No customer messages, Kaspi writes, Google Board writes, DB writes, Telegram sends, cookie/session inspection, raw order IDs, or raw reply text are authorized or exported by this matrix.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path)
    parser.add_argument("--synthesis-closeout", type=Path, default=DEFAULT_SYNTHESIS)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workflow_dir = (args.workflow_dir or _latest_workflow_dir()).resolve()
    output_dir = args.output_dir or (workflow_dir / "automation_options_matrix")
    synthesis_path = args.synthesis_closeout.resolve()
    if args.synthesis_closeout == DEFAULT_SYNTHESIS and not synthesis_path.exists():
        synthesis_path = FALLBACK_SYNTHESIS.resolve()
    manifest = _read_json(workflow_dir / "manifest.json")
    stages = _read_json(workflow_dir / "workflow_stages.json")
    synthesis_text = _read_text(synthesis_path) if synthesis_path.exists() else ""
    rows = build_matrix(
        workflow_manifest=manifest,
        workflow_stages=stages,
        synthesis_text=synthesis_text,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "automation_options_matrix.json", rows)
    _write_csv(output_dir / "automation_options_matrix.csv", rows)
    markdown = _build_markdown(rows, workflow_dir=workflow_dir, synthesis_path=synthesis_path)
    (output_dir / "automation_options_matrix.md").write_text(markdown, encoding="utf-8")
    output_manifest = {
        "gate": "GREEN_AUTOMATION_OPTIONS_MATRIX_BUILT_FROM_REDACTED_EVIDENCE",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_dir": str(workflow_dir),
        "synthesis_closeout": str(synthesis_path),
        "rows": len(rows),
        "recommended_immediate_path": (
            "computer_use_helper_visual_no_send_proof_then_send_canary"
            if any(
                row["option"] == "chrome_profile_session_reuse"
                and row["current_status"] == "EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"
                for row in rows
            )
            else "chrome_profile4_reconnect_then_live_ui_no_send_canary"
        ),
        "recommended_future_path": "direct_chat_api_only_after_safe_payload_side_effect_canary",
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", output_manifest)
    print(json.dumps(output_manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
