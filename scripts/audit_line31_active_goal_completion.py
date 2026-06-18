#!/usr/bin/env python3
"""Audit whether the active LINE31 launch goal is actually complete."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.report_line31_next_launch_action import (  # noqa: E402
    DEFAULT_EXPORTS_ROOT,
    build_report,
)
from scripts.build_line31_current_noncreative_gate_matrix import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT as DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
    build_matrix as build_current_noncreative_matrix,
)
from scripts.validate_line31_launch_readiness import (  # noqa: E402
    DEFAULT_EVIDENCE_ROOT,
    validate_launch_readiness,
)
from scripts.validate_line31_owner_objective_source_freshness import (  # noqa: E402
    DEFAULT_OWNER_FACTS_PATH,
    validate_owner_objective_source_freshness,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_MARKDOWN_OUTPUT = (
    PROJECT_ROOT / "docs" / "current" / "LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md"
)
OWNER_FACTS_PATH = DEFAULT_OWNER_FACTS_PATH
ROUND3_MATRIX_PATH = (
    PROJECT_ROOT
    / "exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/"
    "final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.json"
)
CURRENT_NONCREATIVE_MATRIX_PATH = (
    DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT / "CURRENT_NONCREATIVE_GATE_MATRIX.json"
)
CURRENT_STATUS_PATH = PROJECT_ROOT / "docs/current/LINE31_LAUNCH_CURRENT_STATUS.json"
FINAL_START_DECISION_PREFIX = "line31_final_start_decision_packet_"
FINAL_START_DECISION_MANIFEST = "final_start_decision_manifest.json"
CURRENT_META_GREEN_GATE = "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_NO_WRITE"
CURRENT_ACTIVATION_GREEN_GATE = "GREEN_LINE31_META_ACTIVATE_ONLY_PREFLIGHT_READY_NO_WRITE"
FINAL_START_DECISION_READY_GATE = "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"
EXPERT_INTAKE_CLEAR_GATES = {
    "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE",
    "YELLOW_LINE31_EXPERT_START_AS_IS_PREFLIGHT_REFRESH_REQUIRED_NO_WRITE",
    "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE",
    "YELLOW_LINE31_EXPERT_HOLD_PAUSED_NO_WRITE",
}


def _requirement(
    requirement: str,
    *,
    achieved: bool,
    evidence: str,
    blocker: str = "",
) -> dict[str, Any]:
    return {
        "requirement": requirement,
        "status": "ACHIEVED" if achieved else "PENDING",
        "achieved": achieved,
        "evidence": evidence,
        "blocker": blocker,
    }


def _has_error_containing(errors: list[str], needle: str) -> bool:
    return any(needle in error for error in errors)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _status_by_gate(matrix: dict[str, Any], gate: str) -> dict[str, Any]:
    for row in matrix.get("final_status", []):
        if row.get("gate") == gate:
            return row
    return {}


def _latest_final_start_decision_packet() -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in DEFAULT_EXPORTS_ROOT.glob(f"{FINAL_START_DECISION_PREFIX}*")
            if path.is_dir() and (path / FINAL_START_DECISION_MANIFEST).is_file()
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": "", "manifest": "", "payload": {}}
    current = candidates[0]
    manifest = current / FINAL_START_DECISION_MANIFEST
    return {
        "exists": True,
        "dir": str(current),
        "manifest": str(manifest),
        "payload": _read_json(manifest),
    }


def _current_meta_paused_ready(current_status: dict[str, Any]) -> bool:
    current_meta = current_status.get("latest_meta_current_readonly_snapshot")
    current_meta = current_meta if isinstance(current_meta, dict) else {}
    summary = current_meta.get("current_state_summary")
    summary = summary if isinstance(summary, dict) else {}
    ad_ids = {str(item) for item in (summary.get("ad_ids") or [])}
    return (
        current_status.get("status")
        == "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
        and current_meta.get("gate") == CURRENT_META_GREEN_GATE
        and current_meta.get("checks_failed") == 0
        and current_meta.get("checks_review") == 0
        and current_meta.get("retained_ui_only_gaps") == []
        and summary.get("campaign_status") == "PAUSED"
        and summary.get("adset_status") == "PAUSED"
        and summary.get("ads_by_adset_count") == 3
        and ad_ids
        == {"120245492808400641", "120245488532270641", "120245492808390641"}
        and str(summary.get("adset_daily_budget") or "") == "3093"
        and summary.get("customer_visible_cta") == "ORDER_NOW"
        and summary.get("customer_visible_title") == "AcmeWear 3в1"
        and summary.get("landing_url") == "https://acmewear.pro/line31"
    )


def _current_activation_ready(current_status: dict[str, Any]) -> bool:
    activation = current_status.get("latest_meta_current_activation_preflight")
    activation = activation if isinstance(activation, dict) else {}
    return (
        activation.get("gate") == CURRENT_ACTIVATION_GREEN_GATE
        and activation.get("apply_requested") is False
        and activation.get("meta_write_attempted") is False
        and bool(activation.get("required_meta_write_phrase_path"))
        and bool((activation.get("preflight_evidence_lock") or {}).get("path"))
    )


def _final_start_packet_ready(packet: dict[str, Any]) -> bool:
    payload = packet.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    return (
        packet.get("exists") is True
        and payload.get("gate") == FINAL_START_DECISION_READY_GATE
        and payload.get("checks_failed") == 0
        and payload.get("external_write_attempted") is False
        and payload.get("meta_write_attempted") is False
    )


def _expert_launch_answer_intake_resolved(current_status: dict[str, Any]) -> bool:
    intake = _effective_expert_launch_answer_intake(current_status)
    next_action = intake.get("next_safe_action")
    next_action = next_action if isinstance(next_action, dict) else {}
    return (
        intake.get("gate") in EXPERT_INTAKE_CLEAR_GATES
        and intake.get("decision") in {"START_AS_IS", "CHANGE_BEFORE_START", "HOLD_PAUSED"}
        and bool(next_action.get("action"))
    )


def _effective_expert_launch_answer_intake(current_status: dict[str, Any]) -> dict[str, Any]:
    """Prefer the fresh post-expert sequence intake over stale direct intake pointers."""

    post_sequence = current_status.get("latest_post_expert_answer_sequence")
    post_sequence = post_sequence if isinstance(post_sequence, dict) else {}
    sequence_intake = post_sequence.get("expert_intake")
    sequence_intake = sequence_intake if isinstance(sequence_intake, dict) else {}
    if sequence_intake.get("gate") in EXPERT_INTAKE_CLEAR_GATES:
        return sequence_intake
    intake = current_status.get("latest_expert_launch_answer_intake")
    return intake if isinstance(intake, dict) else {}


def _objective_requirement_rows(
    *,
    current_noncreative_matrix: dict[str, Any] | None,
    owner_source_freshness: dict[str, Any],
) -> list[dict[str, Any]]:
    matrix_for_objective = current_noncreative_matrix or _read_json(
        CURRENT_NONCREATIVE_MATRIX_PATH
    )
    owner_facts = _read_json(OWNER_FACTS_PATH)
    round3_matrix = _read_json(ROUND3_MATRIX_PATH)
    cash = owner_facts.get("cash", {})
    shr = owner_facts.get("shr", {})
    line31_stock = owner_facts.get("line31_stock", {})
    unrelated_row = _status_by_gate(round3_matrix, "unrelated_broad_suite_queue")
    owner_source_ok = owner_source_freshness.get("ok") is True
    owner_source_gate = str(owner_source_freshness.get("gate", "UNKNOWN"))

    current_noncreative_green = (
        matrix_for_objective.get("overall_gate") == "GREEN"
        and matrix_for_objective.get("can_use_green_except_creative") is True
    )
    unrelated_summary = str(unrelated_row.get("evidence_summary", ""))
    option2_achieved = (
        unrelated_row.get("status") == "GREEN"
        and "11 passed" in unrelated_summary
        and "72 passed" in unrelated_summary
        and current_noncreative_green
    )

    cash_source = str(cash.get("source_workbook", ""))
    cash_achieved = (
        owner_source_ok
        and
        cash_source.endswith("Inbound_calendar_V10.002.xlsx")
        and cash.get("current_timestamp") == "2026-06-01 09:06:51 GMT+5"
        and shr.get("po5_payment_18_cny") == 7000
        and shr.get("po5_payment_18_final_exchanger_receipt_pending") is True
    )
    reserve_proof = owner_source_freshness.get("protected_reserve", {})
    reserve_achieved = (
        owner_source_ok
        and reserve_proof.get("ok") is True
        and reserve_proof.get("expected_min_kzt") == 800000
        and reserve_proof.get("owner_fact_min_kzt") == 800000
    )
    stock_achieved = (
        owner_source_ok
        and
        line31_stock.get("basis")
        == "owner-approved exact rebuild from April leftovers plus PO1-A arrival"
        and line31_stock.get("physical_total_stock_qty") == 436
        and line31_stock.get("physical_sellable_stock_qty") == 354
        and line31_stock.get("open_reserved_on_delivery_exposure_qty") == 6
        and line31_stock.get("physical_sellable_available_after_open_reserved_qty") == 348
        and line31_stock.get("physical_not_for_sale_reserve_qty") == 82
        and line31_stock.get("economic_final_sales_estimate_qty") == 432
    )

    return [
        _requirement(
            "Option 2 unrelated-failure repair first is repaired/quarantined",
            achieved=option2_achieved,
            evidence=str(ROUND3_MATRIX_PATH),
            blocker=(
                ""
                if option2_achieved
                else "unrelated repair queue is not green or current non-creative matrix is not green"
            ),
        ),
        _requirement(
            "Owner objective source freshness is green",
            achieved=owner_source_ok,
            evidence=f"{OWNER_FACTS_PATH} via {owner_source_gate}",
            blocker=(
                ""
                if owner_source_ok
                else "; ".join(owner_source_freshness.get("errors", []))
            ),
        ),
        _requirement(
            "Current cash and SHR timing use latest owner workbook truth",
            achieved=cash_achieved,
            evidence=(
                str(
                    owner_source_freshness.get("cash_and_shr", {}).get(
                        "workbook_path", OWNER_FACTS_PATH
                    )
                )
                + f" via {owner_source_gate}"
            ),
            blocker=(
                ""
                if cash_achieved
                else "cash timestamp or SHR #18 7000 CNY paid-with-receipt-pending fact is missing"
            ),
        ),
        _requirement(
            "Protected cash reserve is exactly 800000 KZT",
            achieved=reserve_achieved,
            evidence=f"{OWNER_FACTS_PATH} via {owner_source_gate}",
            blocker=(
                ""
                if reserve_achieved
                else "protected reserve is not exactly 800000 KZT in source freshness proof"
            ),
        ),
        _requirement(
            "Current LINE31 stock uses April leftovers plus PO1-A arrival rebuild",
            achieved=stock_achieved,
            evidence=(
                str(
                    owner_source_freshness.get("line31_stock", {}).get(
                        "source_packet", OWNER_FACTS_PATH
                    )
                )
                + f" via {owner_source_gate}"
            ),
            blocker=(
                ""
                if stock_achieved
                else "LINE31 stock rebuild basis or expected physical/sellable totals are missing"
            ),
        ),
    ]


def _current_launch_control_requirement_rows() -> list[dict[str, Any]]:
    current_status = _read_json(CURRENT_STATUS_PATH)
    final_start_packet = _latest_final_start_decision_packet()
    if _current_meta_paused_ready(current_status) and _current_activation_ready(
        current_status
    ):
        current_meta = current_status.get("latest_meta_current_readonly_snapshot")
        current_meta = current_meta if isinstance(current_meta, dict) else {}
        activation = current_status.get("latest_meta_current_activation_preflight")
        activation = activation if isinstance(activation, dict) else {}
        expert_intake = _effective_expert_launch_answer_intake(current_status)
        traceability = current_status.get("latest_customer_journey_traceability_audit")
        traceability = traceability if isinstance(traceability, dict) else {}
        monitoring = current_status.get("latest_post_publish_monitoring_packet")
        monitoring = monitoring if isinstance(monitoring, dict) else {}
        final_start_ready = _final_start_packet_ready(final_start_packet)
        expert_intake_resolved = _expert_launch_answer_intake_resolved(current_status)
        monitoring_contract = monitoring.get("truth_separation_contract")
        monitoring_contract = (
            monitoring_contract if isinstance(monitoring_contract, list) else []
        )
        monitoring_contract_text = " ".join(str(item) for item in monitoring_contract)
        monitoring_achieved = (
            monitoring.get("gate")
            == "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
            and monitoring.get("external_write_attempted") is False
            and monitoring.get("meta_write_attempted") is False
            and bool(monitoring.get("commands_tsv"))
            and "Meta traffic truth" in monitoring_contract_text
            and "Website truth" in monitoring_contract_text
            and "Redirect truth" in monitoring_contract_text
            and "Kaspi order truth" in monitoring_contract_text
            and "Attribution truth" in monitoring_contract_text
        )
        traceability_achieved = (
            traceability.get("gate")
            == "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
            and traceability.get("checks_failed") == 0
            and int(traceability.get("checks_total") or 0) >= 100
            and traceability.get("external_write_attempted") is False
            and traceability.get("meta_write_attempted") is False
            and bool(traceability.get("checks_csv"))
        )
        return [
            _requirement(
                "Current LINE31 Meta setup is source-verified paused-ready",
                achieved=True,
                evidence=str(current_meta.get("manifest") or CURRENT_STATUS_PATH),
            ),
            _requirement(
                "Meta adset budget currency matches owner-approved KZT intent",
                achieved=True,
                evidence=str(current_meta.get("manifest") or CURRENT_STATUS_PATH),
            ),
            _requirement(
                "Current activate-only preflight is green and no-write",
                achieved=True,
                evidence=str(activation.get("manifest") or CURRENT_STATUS_PATH),
            ),
            _requirement(
                "Final-start decision packet is ready and no-write",
                achieved=final_start_ready,
                evidence=str(final_start_packet.get("manifest") or CURRENT_STATUS_PATH),
                blocker=(
                    ""
                    if final_start_ready
                    else "final-start decision packet missing, failed, or attempted write"
                ),
            ),
            _requirement(
                "External expert launch answer is ingested and classified",
                achieved=expert_intake_resolved,
                evidence=str(expert_intake.get("manifest") or CURRENT_STATUS_PATH),
                blocker=(
                    ""
                    if expert_intake_resolved
                    else (
                        "expert answer is missing, ambiguous, unclassified, or still waiting "
                        "in the Oracle pack Answer folder"
                    )
                ),
            ),
            _requirement(
                "Final owner/expert start decision is recorded and activation is applied",
                achieved=False,
                evidence=str(activation.get("required_meta_write_phrase_path") or CURRENT_STATUS_PATH),
                blocker=(
                    "campaign/adset/three ads are intentionally PAUSED until the final "
                    "owner/expert start decision and exact activate-only approval phrase"
                ),
            ),
            _requirement(
                "Post-publish monitoring plan is ready and truth-separated",
                achieved=monitoring_achieved,
                evidence=str(monitoring.get("manifest") or CURRENT_STATUS_PATH),
                blocker=(
                    ""
                    if monitoring_achieved
                    else "monitoring packet missing, not green, attempted write, or lacks truth-separation contract"
                ),
            ),
            _requirement(
                "Customer journey traceability audit is green",
                achieved=traceability_achieved,
                evidence=str(traceability.get("manifest") or CURRENT_STATUS_PATH),
                blocker=(
                    ""
                    if traceability_achieved
                    else "traceability audit missing, not green, attempted write, or has failed checks"
                ),
            ),
        ]
    bridge = current_status.get("latest_meta_publish_bridge")
    bridge = bridge if isinstance(bridge, dict) else {}
    meta_preflight = current_status.get("latest_meta_line31_publish_preflight")
    meta_preflight = meta_preflight if isinstance(meta_preflight, dict) else {}
    live_stopline = current_status.get("latest_meta_live_write_ready_stopline")
    live_stopline = live_stopline if isinstance(live_stopline, dict) else {}
    partial_blocker = current_status.get("latest_meta_api_live_partial_blocker")
    partial_blocker = partial_blocker if isinstance(partial_blocker, dict) else {}
    budget_stopline = current_status.get("latest_meta_budget_currency_stopline")
    budget_stopline = budget_stopline if isinstance(budget_stopline, dict) else {}
    safety_pause = current_status.get("latest_meta_partial_shell_safety_pause")
    safety_pause = safety_pause if isinstance(safety_pause, dict) else {}
    monitoring = current_status.get("latest_post_publish_monitoring_packet")
    monitoring = monitoring if isinstance(monitoring, dict) else {}
    traceability = current_status.get("latest_customer_journey_traceability_audit")
    traceability = traceability if isinstance(traceability, dict) else {}

    bridge_achieved = (
        bridge.get("gate") == "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE"
        and bridge.get("external_write_attempted") is False
        and bridge.get("meta_write_attempted") is False
        and bool(bridge.get("owner_paste_file"))
        and bool(bridge.get("meta_api_live_write_approval_file"))
    )
    meta_preflight_achieved = (
        meta_preflight.get("gate") == "GREEN_META_LINE31_PUBLISH_PREFLIGHT_READY_NO_WRITE"
        and meta_preflight.get("meta_write_attempted") is False
        and (
            bool(meta_preflight.get("required_meta_write_phrase_path"))
            or meta_preflight.get("required_meta_write_phrase_present") is True
        )
        and bool((meta_preflight.get("preflight_evidence_lock") or {}).get("path"))
    )
    partial_live_blocker_recorded = (
        partial_blocker.get("exists") is True
        and partial_blocker.get("gate")
        == "YELLOW_PARTIAL_META_LAUNCH_BLOCKED_BY_META_APP_DEV_MODE"
        and partial_blocker.get("three_ads_live_verified") is False
    )
    partial_live_write_approved = (
        partial_live_blocker_recorded
        and bool((partial_blocker.get("approval") or {}).get("approval_paste_file"))
        and bool((partial_blocker.get("approval") or {}).get("required_phrase_file"))
    )
    budget_stopline_open = (
        budget_stopline.get("exists") is True
        and budget_stopline.get("gate") == "RED_META_BUDGET_CURRENCY_MISMATCH_STOPLINE"
    )
    safety_pause_verification = safety_pause.get("verification")
    safety_pause_verification = (
        safety_pause_verification if isinstance(safety_pause_verification, dict) else {}
    )
    safety_pause_achieved = (
        safety_pause.get("gate") == "GREEN_LINE31_META_PARTIAL_SHELL_SAFETY_PAUSED"
        and safety_pause_verification.get("campaign_status_paused") is True
        and safety_pause_verification.get("adset_status_paused") is True
    )
    meta_live_write_approved = partial_live_write_approved or (
        meta_preflight.get("gate") == "GREEN_META_LINE31_PUBLISH_APPLIED_VERIFY_REQUIRED"
        and meta_preflight.get("apply_requested") is True
        and meta_preflight.get("meta_write_attempted") is True
        and (meta_preflight.get("write_gate") or {}).get("ok") is True
    )
    meta_live_publish_applied = (
        not partial_live_blocker_recorded
        and not budget_stopline_open
        and meta_live_write_approved
        and isinstance(meta_preflight.get("apply_result"), dict)
        and bool((meta_preflight.get("apply_result") or {}).get("objects"))
    )
    live_apply_blocker = "Meta apply evidence with created campaign, adset, video/image creatives, and three ads is missing"
    if partial_live_blocker_recorded:
        blocker = partial_blocker.get("latest_blocker") or {}
        campaign = partial_blocker.get("campaign") or {}
        adset = partial_blocker.get("adset") or {}
        live_apply_blocker = (
            "Partial Meta shell exists but three ads are not live/source-verified; "
            f"campaign={campaign.get('id', '')}, adset={adset.get('id', '')}; "
            f"latest blocker: {blocker.get('message', '')}"
        )
    if budget_stopline_open:
        observation = budget_stopline.get("owner_observation") or {}
        if safety_pause_achieved:
            live_apply_blocker = (
                "Partial Meta shell is paused and spend risk is contained, but the "
                "budget currency mismatch stopline remains open; owner observed "
                f"{observation.get('observed_budget_display', '')}/day instead of "
                "15,000 KZT/day"
            )
        else:
            live_apply_blocker = (
                "Meta budget currency mismatch stopline is open; owner observed "
                f"{observation.get('observed_budget_display', '')}/day instead of 15,000 KZT/day"
            )
    monitoring_contract = monitoring.get("truth_separation_contract")
    monitoring_contract = monitoring_contract if isinstance(monitoring_contract, list) else []
    monitoring_contract_text = " ".join(str(item) for item in monitoring_contract)
    monitoring_achieved = (
        monitoring.get("gate") == "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
        and monitoring.get("external_write_attempted") is False
        and monitoring.get("meta_write_attempted") is False
        and bool(monitoring.get("commands_tsv"))
        and "Meta traffic truth" in monitoring_contract_text
        and "Website truth" in monitoring_contract_text
        and "Redirect truth" in monitoring_contract_text
        and "Kaspi order truth" in monitoring_contract_text
        and "Attribution truth" in monitoring_contract_text
    )
    traceability_achieved = (
        traceability.get("gate")
        == "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
        and traceability.get("checks_failed") == 0
        and int(traceability.get("checks_total") or 0) >= 100
        and traceability.get("external_write_attempted") is False
        and traceability.get("meta_write_attempted") is False
        and bool(traceability.get("checks_csv"))
    )

    return [
        _requirement(
            "LINE31 Meta publish bridge is green and no-write",
            achieved=bridge_achieved,
            evidence=str(bridge.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if bridge_achieved
                else "publish bridge missing, not green, attempted write, or lacks owner paste files"
            ),
        ),
        _requirement(
            "LINE31 Meta API publish preflight is green and no-write",
            achieved=meta_preflight_achieved,
            evidence=str(meta_preflight.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if meta_preflight_achieved
                else "Meta publish preflight missing, blocked, attempted write, or lacks required phrase file"
            ),
        ),
        _requirement(
            "Exact META_API_LIVE_WRITE approval evidence is recorded and gate-valid",
            achieved=meta_live_write_approved,
            evidence=str(
                partial_blocker.get("manifest")
                or live_stopline.get("manifest")
                or meta_preflight.get("manifest")
                or CURRENT_STATUS_PATH
            ),
            blocker=(
                ""
                if meta_live_write_approved
                else "exact generated META_API_LIVE_WRITE phrase has not been pasted and accepted by write gate"
            ),
        ),
        _requirement(
            "LINE31 Meta campaign/adset/three ads are live-applied through API",
            achieved=meta_live_publish_applied,
            evidence=str(
                partial_blocker.get("manifest")
                or meta_preflight.get("manifest")
                or CURRENT_STATUS_PATH
            ),
            blocker="" if meta_live_publish_applied else live_apply_blocker,
        ),
        _requirement(
            "Meta adset budget currency matches owner-approved KZT intent",
            achieved=not budget_stopline_open,
            evidence=str(budget_stopline.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if not budget_stopline_open
                else (
                    "owner observed Ads Manager budget as $150/day; partial shell is "
                    "safety-paused, but budget must be repaired or rebuilt before any launch retry"
                    if safety_pause_achieved
                    else "owner observed Ads Manager budget as $150/day; launch must pause or repair budget before any retry"
                )
            ),
        ),
        _requirement(
            "Partial LINE31 Meta campaign/adset shell is safety-paused while blockers are resolved",
            achieved=safety_pause_achieved,
            evidence=str(safety_pause.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if safety_pause_achieved
                else "partial campaign/adset shell is not source-verified PAUSED"
            ),
        ),
        _requirement(
            "Post-publish monitoring plan is ready and truth-separated",
            achieved=monitoring_achieved,
            evidence=str(monitoring.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if monitoring_achieved
                else "monitoring packet missing, not green, attempted write, or lacks truth-separation contract"
            ),
        ),
        _requirement(
            "Customer journey traceability audit is green",
            achieved=traceability_achieved,
            evidence=str(traceability.get("manifest") or CURRENT_STATUS_PATH),
            blocker=(
                ""
                if traceability_achieved
                else "traceability audit missing, not green, attempted write, or has failed checks"
            ),
        ),
    ]


def build_completion_audit(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    mapping_path: Path | None = None,
    exports_root: Path = DEFAULT_EXPORTS_ROOT,
    refresh_noncreative_matrix: bool = True,
    noncreative_output_root: Path = DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
) -> dict[str, Any]:
    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    current_noncreative_matrix: dict[str, Any] | None = None
    if refresh_noncreative_matrix:
        current_noncreative_matrix = build_current_noncreative_matrix(
            output_root=noncreative_output_root,
        )
    owner_source_freshness = validate_owner_objective_source_freshness(OWNER_FACTS_PATH)
    report = build_report(
        evidence_root=evidence_root,
        mapping_path=mapping_path,
        exports_root=exports_root,
    )
    current_status = _read_json(CURRENT_STATUS_PATH)
    budget_stopline = current_status.get("latest_meta_budget_currency_stopline")
    budget_stopline = budget_stopline if isinstance(budget_stopline, dict) else {}
    budget_stopline_open = (
        budget_stopline.get("exists") is True
        and budget_stopline.get("gate") == "RED_META_BUDGET_CURRENCY_MISMATCH_STOPLINE"
    )
    effective_mapping_path = Path(report["mapping_path"])
    pending = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=True,
        mapping_path=effective_mapping_path,
    )
    strict = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=False,
        mapping_path=effective_mapping_path,
    )

    strict_errors = strict.errors
    creative_missing = [
        item
        for item in report["missing_or_pending"]
        if item.startswith("assets[") or "creative_ready_declaration" in item
    ]
    approval_missing = (
        _has_error_containing(strict_errors, "publish_authority.approved")
        or _has_error_containing(strict_errors, "approval_evidence")
    )
    approval_achieved = not approval_missing and strict.metrics.get("creative_strict_ok", False)
    final_mapping_achieved = (
        not creative_missing
        and report.get("final_assets_ready") is True
        and report.get("live_tracking_green") is True
    )
    internal_kaspi_policy_achieved = (
        "KEEP_INTERNAL_KASPI_LINE31_CAMPAIGNS_ON" in report["internal_kaspi_policy"]
    )

    requirements = [
        _requirement(
            "Non-creative LINE31 launch readiness remains green",
            achieved=pending.ok,
            evidence=f"validate_line31_launch_readiness --allow-pending-creative => {pending.gate}",
            blocker="; ".join(pending.errors),
        ),
        *_objective_requirement_rows(
            current_noncreative_matrix=current_noncreative_matrix,
            owner_source_freshness=owner_source_freshness,
        ),
        _requirement(
            "Final creative asset mapping is filled and hash-verified",
            achieved=final_mapping_achieved,
            evidence=str(report["mapping_path"]),
            blocker="" if final_mapping_achieved else ", ".join(creative_missing),
        ),
        *_current_launch_control_requirement_rows(),
        _requirement(
            "Exact owner Meta publish approval evidence is recorded and SHA-verified",
            achieved=approval_achieved,
            evidence=str(report["approval_phrase_path"]),
            blocker="" if approval_achieved else "approval evidence is missing or not strict-valid",
        ),
        _requirement(
            "Strict LINE31 launch readiness passes",
            achieved=strict.ok,
            evidence=f"validate_line31_launch_readiness => {strict.gate}",
            blocker="; ".join(strict.errors),
        ),
        _requirement(
            "Internal Kaspi LINE31 campaigns remain protected unless separately approved",
            achieved=internal_kaspi_policy_achieved,
            evidence=report["internal_kaspi_policy"],
            blocker=(
                ""
                if internal_kaspi_policy_achieved
                else "internal Kaspi protection policy missing from next-action report"
            ),
        ),
    ]
    complete = all(row["achieved"] for row in requirements)
    requirement_status = {row["requirement"]: row["status"] for row in requirements}
    next_action = report["next_action"]
    if (
        requirement_status.get("External expert launch answer is ingested and classified")
        == "PENDING"
    ):
        current_status = _read_json(CURRENT_STATUS_PATH)
        intake = current_status.get("latest_expert_launch_answer_intake")
        intake = intake if isinstance(intake, dict) else {}
        post_sequence = current_status.get("latest_post_expert_answer_sequence")
        post_sequence = post_sequence if isinstance(post_sequence, dict) else {}
        answer_dir = str(intake.get("answer_dir") or "")
        sequence_command = str(
            post_sequence.get("sequence_command")
            or "python3 scripts/run_line31_post_expert_answer_sequence.py --json"
        )
        next_action = (
            "Send the Oracle pack to the external expert if not already sent. After the "
            "answer lands, save it into the Oracle pack Answer folder"
            f"{(': ' + answer_dir) if answer_dir else ''}, then run "
            f"`{sequence_command}`. This wrapper classifies the answer, refreshes the "
            "current LINE31 status, refreshes the completion audit, and writes the next "
            "safe action. Do not activate until the answer is classified and the final "
            "exact activate-only approval path is used."
        )
    elif (
        requirement_status.get(
            "Final owner/expert start decision is recorded and activation is applied"
        )
        == "PENDING"
    ):
        current_status = _read_json(CURRENT_STATUS_PATH)
        activation = current_status.get("latest_meta_current_activation_preflight")
        activation = activation if isinstance(activation, dict) else {}
        expert_intake = _effective_expert_launch_answer_intake(current_status)
        expert_decision = str(expert_intake.get("decision") or "")
        phrase_path = str(activation.get("required_meta_write_phrase_path") or "")
        if expert_decision == "CHANGE_BEFORE_START":
            next_action = (
                "External expert answer is classified as CHANGE_BEFORE_START. Keep the LINE31 "
                "Meta campaign/adset/three ads paused, record the owner-updated facts "
                "(internal Kaspi campaigns paused at 04.06.2026_12_14_49, Meta budget "
                "currency is USD, LINE31 stock anchor/backfill rule), complete the bounded "
                "same-day prelaunch checks, then rerun current Meta snapshot and "
                "activate-only preflight before asking for the final activation phrase. "
                f"Use the current activation phrase path only after those checks: {phrase_path}."
            )
        elif expert_decision == "HOLD_PAUSED":
            next_action = (
                "External expert answer is classified as HOLD_PAUSED. Keep LINE31 Meta paused "
                "and do not request activation until a new scoped repair/review packet clears "
                "the retained blockers."
            )
        else:
            next_action = (
                "Current LINE31 Meta setup is source-verified and paused-ready. Wait for the "
                "external expert/owner final start decision. If the decision is START_AS_IS, "
                "use the exact activate-only approval phrase path: "
                f"{phrase_path}. If any setting changes first, rerun the current Meta snapshot "
                "and activate-only preflight before activation."
            )
    elif (
        requirement_status.get("Meta adset budget currency matches owner-approved KZT intent")
        == "PENDING"
    ):
        safety_pause_achieved = (
            requirement_status.get(
                "Partial LINE31 Meta campaign/adset shell is safety-paused while blockers are resolved"
            )
            == "ACHIEVED"
        )
        if safety_pause_achieved:
            next_action = (
                "Keep the partial LINE31 Meta shell paused. Approve a currency-corrected budget "
                "repair or clean rebuild after fresh preflight, then resolve the Meta app-mode "
                "creative blocker or use an owner-approved UI fallback before creating ads."
            )
        else:
            next_action = (
                "Stop LINE31 Meta launch execution. Approve either a safety pause for the partial "
                "campaign/adset shell or a currency-corrected budget repair after fresh preflight; "
                "do not create ads or retry API/UI launch while the budget stopline is open."
            )
    elif (
        requirement_status.get(
            "Exact META_API_LIVE_WRITE approval evidence is recorded and gate-valid"
        )
        == "PENDING"
    ):
        next_action = (
            "Paste the exact META_API_LIVE_WRITE approval phrase generated by the latest "
            "green LINE31 Meta publish preflight, then run the approved Meta API apply command."
        )
    elif (
        requirement_status.get("LINE31 Meta campaign/adset/three ads are live-applied through API")
        == "PENDING"
    ):
        next_action = (
            "Run the approved LINE31 Meta API apply command, then verify created campaign, adset, "
            "three ads, and post-publish tracking."
        )

    return {
        "generated_at": generated_at,
        "complete": complete,
        "gate": "COMPLETE_READY_FOR_OWNER_APPROVED_META_PUBLISH" if complete else "INCOMPLETE",
        "evidence_root": str(evidence_root),
        "mapping": report["mapping_path"],
        "pending_gate": pending.gate,
        "pending_ok": pending.ok,
        "strict_gate": strict.gate,
        "strict_ok": strict.ok,
        "ready_to_publish": bool(report["ready_to_publish"] and not budget_stopline_open),
        "current_noncreative_matrix_refreshed": refresh_noncreative_matrix,
        "current_noncreative_matrix": current_noncreative_matrix,
        "owner_objective_source_freshness": owner_source_freshness,
        "requirements": requirements,
        "missing_or_pending": report["missing_or_pending"],
        "next_action": next_action,
        "one_shot_example_command": report["one_shot_example_command"],
        "starter_prompt": report["starter_prompt"],
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Active Goal Completion Audit",
        "",
        f"Generated: {audit['generated_at']}",
        "",
        f"Gate: `{audit['gate']}`",
        f"Complete: `{str(audit['complete']).lower()}`",
        f"Ready to publish: `{str(audit['ready_to_publish']).lower()}`",
        "",
        "## Current Non-Creative Matrix",
        "",
        f"Refreshed: `{str(audit['current_noncreative_matrix_refreshed']).lower()}`",
    ]
    if audit["current_noncreative_matrix"]:
        matrix = audit["current_noncreative_matrix"]
        lines.extend(
            [
                f"Overall gate: `{matrix['overall_gate']}`",
                f"Can use GREEN_EXCEPT_CREATIVE: `{str(matrix['can_use_green_except_creative']).lower()}`",
                f"Evidence root: `{matrix['evidence_root']}`",
            ]
        )
    lines.extend(
        [
            "",
        "## Requirement Status",
        "",
        "| requirement | status | evidence | blocker |",
        "| --- | --- | --- | --- |",
        ]
    )
    for row in audit["requirements"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["requirement"]),
                    f"`{row['status']}`",
                    f"`{row['evidence']}`",
                    str(row["blocker"] or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            audit["next_action"],
            "",
            "## Preferred One-Shot Command",
            "",
            "```bash",
            audit["one_shot_example_command"],
            "```",
            "",
            "## Starter Prompt",
            "",
            "```text",
            audit["starter_prompt"],
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--exports-root", type=Path, default=DEFAULT_EXPORTS_ROOT)
    parser.add_argument("--mapping", type=Path, default=None)
    parser.add_argument(
        "--noncreative-output-root",
        type=Path,
        default=DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
        help="Output root for the current non-creative validator matrix refresh.",
    )
    parser.add_argument(
        "--skip-noncreative-refresh",
        action="store_true",
        help="Do not refresh current non-creative validators before auditing completion.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-markdown",
        type=Path,
        default=None,
        help=(
            "Write the human-readable audit Markdown to a file while preserving the "
            "normal stdout format."
        ),
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit 0 even when the audit proves the goal is incomplete.",
    )
    args = parser.parse_args(argv)

    audit = build_completion_audit(
        evidence_root=args.evidence_root,
        exports_root=args.exports_root,
        mapping_path=args.mapping,
        refresh_noncreative_matrix=not args.skip_noncreative_refresh,
        noncreative_output_root=args.noncreative_output_root,
    )
    markdown = _markdown(audit)
    if args.write_markdown:
        args.write_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.write_markdown.write_text(markdown, encoding="utf-8")
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(markdown)
    if audit["complete"] or args.allow_incomplete:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
