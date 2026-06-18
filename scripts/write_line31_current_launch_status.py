#!/usr/bin/env python3
"""Write a stable current LINE31 launch-status pointer for operators."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.report_line31_next_launch_action import build_report  # noqa: E402
from scripts.validate_line31_launch_readiness import DEFAULT_EVIDENCE_ROOT  # noqa: E402


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_EXPORTS_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_META_EXPORTS_ROOT = (
    Path("~/Docs/Business_3/Facebook_ads/exports/validation")
)
DEFAULT_WEB_REPORTS_ROOT = Path("~/Docs/acmewear_web_v2/docs/90_REPORTS")
DEFAULT_AGENT_HANDOFFS_ROOT = Path("~/Docs/Autonomous_business_agent_handoffs")
DEFAULT_JSON_PATH = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_MD_PATH = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.md"
STRICT_OWNER_STATUS = "YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA"
META_APPROVAL_OWNER_STATUS = "YELLOW_STRICT_PUBLISH__PENDING_EXACT_META_APPROVAL"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_manifest(
    *,
    exports_root: Path,
    dir_prefix: str,
    manifest_name: str,
) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in exports_root.glob(f"{dir_prefix}*")
            if path.is_dir() and (path / manifest_name).is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": None, "manifest": None, "payload": {}}

    current = candidates[0]
    manifest = current / manifest_name
    return {
        "exists": True,
        "dir": str(current),
        "manifest": str(manifest),
        "payload": _load_json(manifest),
    }


def _latest_meta_api_preflight(*, exports_root: Path) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in exports_root.glob("meta_api_primary_preflight_*")
            if path.is_dir() and (path / "manifest.json").is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": None, "manifest": None, "payload": {}}

    loaded = [
        {
            "exists": True,
            "dir": str(path),
            "manifest": str(path / "manifest.json"),
            "payload": _load_json(path / "manifest.json"),
        }
        for path in candidates
    ]
    live_readonly = [
        item for item in loaded if item["payload"].get("live_readonly") is True
    ]
    return (live_readonly or loaded)[0]


def _latest_meta_publish_preflight(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_publish_preflight_",
        manifest_name="manifest.json",
    )


def _latest_meta_current_readonly_snapshot(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_current_readonly_api_snapshot_",
        manifest_name="manifest.json",
    )


def _latest_meta_current_activation_preflight(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_current_activation_preflight_",
        manifest_name="manifest.json",
    )


def _latest_meta_launch_identity_discovery(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="meta_launch_identity_discovery_",
        manifest_name="identity_discovery_manifest.json",
    )


def _latest_deploy_liveqa_sequence(*, exports_root: Path) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in exports_root.glob("line31_deploy_liveqa_readiness_sequence_*")
            if path.is_dir() and (path / "sequence_manifest.json").is_file()
        ),
        key=lambda path: ((path / "sequence_manifest.json").stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": None, "manifest": None, "payload": {}}
    current = candidates[0]
    manifest = current / "sequence_manifest.json"
    return {
        "exists": True,
        "dir": str(current),
        "manifest": str(manifest),
        "payload": _load_json(manifest),
    }


def _latest_meta_publish_bridge(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_publish_bridge_",
        manifest_name="bridge_manifest.json",
    )


def _latest_post_publish_monitoring_packet(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_post_publish_monitoring_packet_",
        manifest_name="post_publish_monitoring_manifest.json",
    )


def _latest_expert_launch_answer_intake(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_expert_launch_answer_intake_",
        manifest_name="expert_answer_intake_manifest.json",
    )


def _latest_post_expert_answer_sequence(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_post_expert_answer_sequence_",
        manifest_name="post_expert_answer_sequence_manifest.json",
    )


def _latest_meta_live_write_ready_stopline(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_live_write_ready_stopline_",
        manifest_name="manifest.json",
    )


def _latest_meta_api_live_partial_blocker(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_api_live_partial_blocker_",
        manifest_name="manifest.json",
    )


def _latest_meta_budget_currency_stopline(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_budget_currency_stopline_",
        manifest_name="manifest.json",
    )


def _latest_meta_partial_shell_safety_pause(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_meta_partial_shell_safety_pause_",
        manifest_name="manifest.json",
    )


def _gate_from_markdown(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith("Gate:"):
            return stripped.split(":", 1)[1].strip().strip("`")
    return ""


def _latest_line31_meta_rescue(*, handoffs_root: Path) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in handoffs_root.glob("*_line31_meta_30min_rescue")
            if path.is_dir()
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": None, "files": {}, "synthesis": {}}

    current = candidates[0]
    synthesis_candidates = sorted(
        current.glob("ORCHESTRATOR_RESCUE_SYNTHESIS_*.md"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    synthesis = synthesis_candidates[0] if synthesis_candidates else None
    expected_files = {
        "agent1_budget_repair": "agent1_budget_repair_controller_closeout.md",
        "agent2_three_ad_route": "agent2_three_ad_creation_controller_closeout.md",
        "agent4_ui_fallback": "agent4_app_mode_ui_fallback_prep_closeout.md",
        "agent4_ui_fallback_recovery": "agent4_app_mode_ui_fallback_prep_recovery_note.md",
        "agent5_monitoring_scaffold": "agent5_final_monitoring_scaffold_closeout.md",
    }
    files: dict[str, dict[str, Any]] = {}
    for key, filename in expected_files.items():
        path = current / filename
        files[key] = {
            "exists": path.is_file(),
            "path": str(path),
            "gate": _gate_from_markdown(path) if path.is_file() else "",
        }
    return {
        "exists": True,
        "dir": str(current),
        "synthesis": {
            "exists": synthesis is not None,
            "path": str(synthesis) if synthesis else "",
            "gate": _gate_from_markdown(synthesis) if synthesis else "",
        },
        "files": files,
    }


def _latest_customer_journey_traceability_audit(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_customer_journey_traceability_audit_",
        manifest_name="traceability_manifest.json",
    )


def _latest_line31_live_customer_label_probe(*, exports_root: Path) -> dict[str, Any]:
    return _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_live_customer_label_probe_",
        manifest_name="manifest.json",
    )


def _current_meta_snapshot_green(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("gate") or "").startswith(
            "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED"
        )
        and payload.get("checks_failed") == 0
    )


def _current_meta_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("current_state_summary")
    return summary if isinstance(summary, dict) else {}


def _current_meta_has_three_ads(payload: dict[str, Any]) -> bool:
    summary = _current_meta_summary(payload)
    return _current_meta_snapshot_green(payload) and summary.get("ads_by_adset_count") == 3


def _current_meta_budget_repaired(payload: dict[str, Any]) -> bool:
    summary = _current_meta_summary(payload)
    return _current_meta_snapshot_green(payload) and str(summary.get("adset_daily_budget") or "") == "3093"


def _current_meta_paused_prestart(payload: dict[str, Any]) -> bool:
    summary = _current_meta_summary(payload)
    return (
        _current_meta_snapshot_green(payload)
        and summary.get("campaign_status") == "PAUSED"
        and summary.get("adset_status") == "PAUSED"
    )


def _live_customer_label_green(payload: dict[str, Any]) -> bool:
    return (
        payload.get("gate") == "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
        and payload.get("checks_failed") == 0
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest_web_wrangler_dryrun(*, web_reports_root: Path) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in web_reports_root.glob("line31_wrangler_dryrun_*")
            if path.is_dir() and (path / "closeout.md").is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    if not candidates:
        return {"exists": False, "dir": None, "closeout": None}
    current = candidates[0]
    log_path = current / "wrangler_dryrun.log"
    bundle_index = current / "bundle" / "index.js"
    return {
        "exists": True,
        "dir": str(current),
        "closeout": str(current / "closeout.md"),
        "gate": "GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY",
        "log_path": str(log_path) if log_path.is_file() else "",
        "log_sha256": _sha256(log_path) if log_path.is_file() else "",
        "bundle_index_path": str(bundle_index) if bundle_index.is_file() else "",
        "bundle_index_sha256": _sha256(bundle_index) if bundle_index.is_file() else "",
    }


def _sequence_ready_for_meta_approval(sequence_payload: dict[str, Any]) -> bool:
    mapping_validation = sequence_payload.get("mapping_validation")
    if not isinstance(mapping_validation, dict):
        return False
    return (
        sequence_payload.get("gate")
        == "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE"
        and mapping_validation.get("expected_pending_meta_approval_only") is True
        and bool(sequence_payload.get("meta_publish_approval_phrase"))
    )


def _sequence_mapping_errors(sequence_payload: dict[str, Any]) -> list[str]:
    mapping_validation = sequence_payload.get("mapping_validation")
    if not isinstance(mapping_validation, dict):
        return []
    payload = mapping_validation.get("validator_payload")
    if not isinstance(payload, dict):
        return []
    errors = payload.get("errors")
    return [str(item) for item in errors] if isinstance(errors, list) else []


def build_current_status(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    exports_root: Path = DEFAULT_EXPORTS_ROOT,
    meta_exports_root: Path = DEFAULT_META_EXPORTS_ROOT,
    web_reports_root: Path = DEFAULT_WEB_REPORTS_ROOT,
    agent_handoffs_root: Path = DEFAULT_AGENT_HANDOFFS_ROOT,
) -> dict[str, Any]:
    report = build_report(evidence_root=evidence_root, exports_root=exports_root)
    latest_preflight = _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_final_launch_preflight_",
        manifest_name="line31_launch_preflight_manifest.json",
    )
    latest_drop_intake = _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_final_creative_drop_intake_",
        manifest_name="line31_final_creative_drop_intake_manifest.json",
    )
    latest_final_creative_assets = _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_final_creative_assets_",
        manifest_name="manifest.json",
    )
    latest_web_deploy_approval = _latest_manifest(
        exports_root=exports_root,
        dir_prefix="line31_web_deploy_approval_packet_",
        manifest_name="deploy_preflight_manifest.json",
    )
    latest_meta_api_preflight = _latest_meta_api_preflight(
        exports_root=meta_exports_root,
    )
    latest_meta_publish_preflight = _latest_meta_publish_preflight(
        exports_root=meta_exports_root,
    )
    latest_meta_current_readonly_snapshot = _latest_meta_current_readonly_snapshot(
        exports_root=meta_exports_root,
    )
    latest_meta_current_activation_preflight = _latest_meta_current_activation_preflight(
        exports_root=meta_exports_root,
    )
    latest_meta_launch_identity_discovery = _latest_meta_launch_identity_discovery(
        exports_root=meta_exports_root,
    )
    latest_deploy_liveqa_sequence = _latest_deploy_liveqa_sequence(
        exports_root=exports_root,
    )
    latest_meta_publish_bridge = _latest_meta_publish_bridge(
        exports_root=exports_root,
    )
    latest_post_publish_monitoring_packet = _latest_post_publish_monitoring_packet(
        exports_root=exports_root,
    )
    latest_expert_launch_answer_intake = _latest_expert_launch_answer_intake(
        exports_root=exports_root,
    )
    latest_post_expert_answer_sequence = _latest_post_expert_answer_sequence(
        exports_root=exports_root,
    )
    latest_meta_live_write_ready_stopline = _latest_meta_live_write_ready_stopline(
        exports_root=exports_root,
    )
    latest_meta_api_live_partial_blocker = _latest_meta_api_live_partial_blocker(
        exports_root=exports_root,
    )
    latest_meta_budget_currency_stopline = _latest_meta_budget_currency_stopline(
        exports_root=exports_root,
    )
    latest_meta_partial_shell_safety_pause = _latest_meta_partial_shell_safety_pause(
        exports_root=exports_root,
    )
    latest_customer_journey_traceability_audit = _latest_customer_journey_traceability_audit(
        exports_root=exports_root,
    )
    latest_line31_live_customer_label_probe = _latest_line31_live_customer_label_probe(
        exports_root=exports_root,
    )
    latest_web_wrangler_dryrun = _latest_web_wrangler_dryrun(
        web_reports_root=web_reports_root,
    )
    latest_line31_meta_rescue = _latest_line31_meta_rescue(
        handoffs_root=agent_handoffs_root,
    )
    latest_sequence_payload = latest_deploy_liveqa_sequence["payload"]
    sequence_meta_ready = _sequence_ready_for_meta_approval(latest_sequence_payload)
    sequence_mapping_errors = _sequence_mapping_errors(latest_sequence_payload)
    latest_sequence_mapping_path = str(latest_sequence_payload.get("output_mapping") or "").strip()
    latest_sequence_phrase_path = ""
    if latest_deploy_liveqa_sequence["dir"]:
        maybe_phrase = Path(latest_deploy_liveqa_sequence["dir"]) / "NEXT_META_PUBLISH_APPROVAL_PHRASE.txt"
        latest_sequence_phrase_path = str(maybe_phrase) if maybe_phrase.is_file() else ""
    latest_meta_publish_payload = latest_meta_publish_preflight["payload"]
    latest_meta_publish_gate = str(latest_meta_publish_payload.get("gate") or "")
    latest_meta_current_payload = latest_meta_current_readonly_snapshot["payload"]
    latest_activation_payload = latest_meta_current_activation_preflight["payload"]
    latest_activation_gate = str(latest_activation_payload.get("gate") or "")
    current_meta_three_ads = _current_meta_has_three_ads(latest_meta_current_payload)
    current_meta_budget_ok = _current_meta_budget_repaired(latest_meta_current_payload)
    current_meta_paused = _current_meta_paused_prestart(latest_meta_current_payload)
    current_meta_retained_ui_gaps = latest_meta_current_payload.get(
        "retained_ui_only_gaps"
    )
    current_meta_retained_ui_gaps = (
        current_meta_retained_ui_gaps
        if isinstance(current_meta_retained_ui_gaps, list)
        else []
    )
    live_customer_label_ok = _live_customer_label_green(
        latest_line31_live_customer_label_probe["payload"]
    )
    latest_meta_write_phrase_path = ""
    if latest_meta_publish_preflight["dir"]:
        maybe_meta_phrase = (
            Path(latest_meta_publish_preflight["dir"])
            / "REQUIRED_EXACT_META_API_LIVE_WRITE_APPROVAL_PHRASE.txt"
        )
        latest_meta_write_phrase_path = str(maybe_meta_phrase) if maybe_meta_phrase.is_file() else ""
    latest_final_creative_payload = latest_final_creative_assets["payload"]
    latest_final_creative_rows = latest_final_creative_payload.get("assets") or []
    effective_mapping_path = latest_sequence_mapping_path or report["mapping_path"]
    effective_missing_or_pending = report["missing_or_pending"]
    effective_next_action = report["next_action"]
    effective_owner_status = STRICT_OWNER_STATUS
    effective_status = report["status"]
    effective_ready_to_publish = report["ready_to_publish"]
    effective_pending_gate = report["pending_gate"]
    if sequence_meta_ready and not report["ready_to_publish"]:
        effective_status = "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE"
        effective_owner_status = META_APPROVAL_OWNER_STATUS
        effective_pending_gate = latest_sequence_payload.get("gate") or effective_pending_gate
        effective_missing_or_pending = sequence_mapping_errors or [
            "publish_authority.approved must be true for publish readiness"
        ]
        effective_next_action = (
            "Paste the exact LINE31_COUNTRYWIDE_META_PUBLISH approval phrase generated by "
            "the latest deploy/live-QA sequence, then record approval evidence and run "
            "Meta publish preflight before any Meta write."
        )
    if (
        report["ready_to_publish"]
        and latest_meta_publish_gate == "GREEN_META_LINE31_PUBLISH_PREFLIGHT_READY_NO_WRITE"
    ):
        effective_status = "GREEN_READY_FOR_EXACT_META_API_LIVE_WRITE_APPROVAL_NO_WRITE"
        effective_owner_status = (
            "GREEN_STRICT_READY__PENDING_EXACT_META_API_LIVE_WRITE_APPROVAL"
        )
        effective_pending_gate = latest_meta_publish_gate
        effective_missing_or_pending = [
            "exact META_API_LIVE_WRITE approval phrase must be pasted before Graph API write"
        ]
        effective_next_action = (
            "Paste the exact META_API_LIVE_WRITE approval phrase generated by the latest "
            "LINE31 Meta publish preflight, then run the apply command; after publish, run "
            "post-publish synthetic tracking/redirect QA and read-only monitoring."
        )
    if latest_meta_api_live_partial_blocker["exists"] and not current_meta_three_ads:
        blocker_gate = str(latest_meta_api_live_partial_blocker["payload"].get("gate") or "")
        effective_status = blocker_gate or "YELLOW_PARTIAL_META_LAUNCH_BLOCKED"
        effective_ready_to_publish = False
        effective_owner_status = "YELLOW_PARTIAL_META_SHELL_EXISTS__THREE_ADS_NOT_LIVE"
        effective_pending_gate = blocker_gate or effective_pending_gate
        effective_missing_or_pending = [
            "three LINE31 Meta ads are not live/source-verified",
            "Meta API creative creation is blocked because the Ads_ACMEWEAR app is in development mode",
            "next path requires either Meta app live/public mode or an approved Ads Manager UI fallback",
        ]
        effective_next_action = (
            "Do not declare launch complete. Wait for Meta API rate-limit cooldown, then either make "
            "the Ads_ACMEWEAR app public/live and rerun the idempotent API apply, or approve a Chrome/"
            "Ads Manager UI fallback to create exactly the three ads under the existing LINE31 campaign/adset."
        )
    if latest_meta_budget_currency_stopline["exists"] and not current_meta_budget_ok:
        budget_gate = str(latest_meta_budget_currency_stopline["payload"].get("gate") or "")
        effective_status = budget_gate or "RED_META_BUDGET_CURRENCY_MISMATCH_STOPLINE"
        effective_ready_to_publish = False
        effective_owner_status = "RED_META_BUDGET_CURRENCY_MISMATCH__NO_FURTHER_LAUNCH"
        effective_pending_gate = budget_gate or effective_pending_gate
        effective_missing_or_pending = [
            "Meta Ads Manager shows the LINE31 adset budget as $150/day, not 15,000 KZT/day",
            "owner-approved budget intent must be reconciled with the ad account currency",
            "partial LINE31 campaign/adset shell must be paused or corrected with exact owner approval before any retry",
        ]
        effective_next_action = (
            "Stop LINE31 Meta launch execution. Either approve pausing only the partial LINE31 "
            "campaign/adset shell, or approve a currency-corrected budget repair for the "
            "existing adset after fresh preflight. Do not create ads or retry API/UI launch "
            "while this RED stopline is open."
        )
    if latest_meta_partial_shell_safety_pause["exists"] and not (
        current_meta_three_ads and current_meta_budget_ok
    ):
        pause_gate = str(latest_meta_partial_shell_safety_pause["payload"].get("gate") or "")
        pause_ok = pause_gate == "GREEN_LINE31_META_PARTIAL_SHELL_SAFETY_PAUSED"
        if pause_ok:
            effective_status = "YELLOW_META_PARTIAL_SHELL_PAUSED_BUDGET_REPAIR_PENDING"
            effective_owner_status = "YELLOW_SAFE_PAUSED__BUDGET_AND_APP_BLOCKERS_REMAIN"
            effective_pending_gate = pause_gate
            effective_ready_to_publish = False
            effective_missing_or_pending = [
                "partial LINE31 Meta campaign/adset shell is paused and spend-risk is contained",
                "Meta adset still has the previously unsafe budget payload and must be repaired or rebuilt before launch",
                "Meta app development-mode creative blocker still needs app-live or approved UI fallback resolution",
                "three LINE31 Meta ads are not live/source-verified",
            ]
            effective_next_action = (
                "Keep the paused shell paused. Next, run/read a currency-safe Meta preflight and either "
                "repair/rebuild the paused shell with exact owner approval, then solve the app-mode/UI "
                "fallback path before creating exactly three ads."
            )
    latest_web_deploy_payload = latest_web_deploy_approval["payload"]
    latest_web_live_probe = latest_web_deploy_payload.get("live_probe_before_deploy")
    if (
        not live_customer_label_ok
        and
        isinstance(latest_web_live_probe, dict)
        and latest_web_live_probe.get("contains_forbidden_customer_copy") is True
        and latest_web_live_probe.get("contains_required_customer_copy") is False
    ):
        effective_status = "YELLOW_WEB_CUSTOMER_LABEL_DEPLOY_PENDING__META_SHELL_PAUSED_SAFE"
        effective_owner_status = "YELLOW_WEB_DEPLOY_REQUIRED_BEFORE_META_ACTIVATION"
        effective_ready_to_publish = False
        effective_pending_gate = (
            latest_web_deploy_payload.get("gate")
            or latest_meta_partial_shell_safety_pause["payload"].get("gate")
            or effective_pending_gate
        )
        effective_missing_or_pending = [
            "live https://acmewear.pro/line31 still shows customer-visible ACMEWEAR LINE31 copy",
            "deploy corrected AcmeWear 3в1 website build after exact owner approval",
            "run post-deploy live tracking/redirect QA and wire the new QA evidence",
            "Meta campaign/adset shell is paused and safe, but exactly three LINE31 ads still do not exist",
        ]
        effective_next_action = (
            "Paste the exact ACMEWEAR_WEB_LINE31_DEPLOY_AND_POSTDEPLOY_LIVE_QA approval phrase "
            "from the latest customer-label deploy packet, deploy the corrected website, and "
            "run post-deploy live tracking/redirect QA. Do not create or activate Meta ads until "
            "the live site proves customer-visible copy is AcmeWear 3в1."
        )
    if current_meta_three_ads and current_meta_budget_ok and current_meta_paused:
        effective_status = "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
        effective_owner_status = (
            "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION"
        )
        effective_pending_gate = latest_meta_current_payload.get("gate") or effective_pending_gate
        effective_ready_to_publish = False
        effective_missing_or_pending = [
            "LINE31 Meta campaign, ad set, and exactly three ads are source-verified but still PAUSED",
            "final launch/start decision remains pending before activation",
        ]
        if current_meta_retained_ui_gaps:
            effective_missing_or_pending.append(
                "UI-only Meta settings still need owner/expert review: "
                + ", ".join(str(item) for item in current_meta_retained_ui_gaps)
            )
        if not live_customer_label_ok:
            effective_missing_or_pending.append(
                "live LINE31 customer-visible landing label proof is missing or not green"
            )
        if current_meta_retained_ui_gaps:
            effective_next_action = (
                "Use the latest current Meta API snapshot as the source-backed setup proof. "
                "Before activating, resolve or explicitly accept the UI-only Meta setting gap, "
                "verify the live LINE31 landing label proof is green, and use the external-expert/"
                "owner final start decision for any live activation."
            )
        else:
            activation_phrase_path = str(
                latest_activation_payload.get("required_meta_write_phrase_path") or ""
            )
            effective_next_action = (
                "Use the latest current Meta API snapshot as the source-backed setup proof. "
                "The campaign/adset/three ads are configured and paused; before activation, "
                "keep the live LINE31 landing label proof green and use the external-expert/"
                "owner final start decision for any live activation."
            )
            if latest_activation_gate == "GREEN_LINE31_META_ACTIVATE_ONLY_PREFLIGHT_READY_NO_WRITE":
                effective_next_action += (
                    " The latest activate-only preflight is GREEN; if the owner decides "
                    "to start, use its exact activation approval phrase path: "
                    f"{activation_phrase_path}."
                )

    return {
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "status": effective_status,
        "owner_facing_publish_status": effective_owner_status,
        "post_expert_integration_status": "INTEGRATED_STRICT_GATE_ADDENDUM_20260602",
        "ready_to_publish": effective_ready_to_publish,
        "strict_gate": report["strict_gate"],
        "pending_gate": effective_pending_gate,
        "noncreative_blockers": report["noncreative_blockers"],
        "missing_or_pending": effective_missing_or_pending,
        "next_action": effective_next_action,
        "mapping_path": effective_mapping_path,
        "approval_phrase_path": report["approval_phrase_path"],
        "starter_prompt": report["starter_prompt"],
        "one_shot_example_command": report["one_shot_example_command"],
        "current_drop_validator_command": report["current_drop_validator_command"],
        "standalone_approval_recorder_example_command": report[
            "standalone_approval_recorder_example_command"
        ],
        "deploy_liveqa_sequence_plan_command": (
            "python3 scripts/run_line31_deploy_liveqa_readiness_sequence.py --json"
        ),
        "deploy_liveqa_sequence_execute_command": (
            "python3 scripts/run_line31_deploy_liveqa_readiness_sequence.py "
            "--approval-text-file /absolute/path/to/exact_deploy_liveqa_approval.txt "
            "--execute-approved-deploy-liveqa --json"
        ),
        "approval_evidence_requirement": report["approval_evidence_requirement"],
        "internal_kaspi_policy": report["internal_kaspi_policy"],
        "latest_preflight_packet": {
            "exists": latest_preflight["exists"],
            "dir": latest_preflight["dir"],
            "manifest": latest_preflight["manifest"],
            "gate": latest_preflight["payload"].get("gate"),
            "ready_to_publish": latest_preflight["payload"].get("ready_to_publish"),
            "generated_at": latest_preflight["payload"].get("generated_at"),
        },
        "latest_drop_intake": {
            "exists": latest_drop_intake["exists"],
            "dir": latest_drop_intake["dir"],
            "manifest": latest_drop_intake["manifest"],
            "asset_dir": latest_drop_intake["payload"].get("asset_dir"),
            "approval_text_file": latest_drop_intake["payload"].get("approval_text_file"),
            "checklist_path": latest_drop_intake["payload"].get("checklist_path"),
            "drop_validator_command": latest_drop_intake["payload"].get(
                "drop_validator_command"
            ),
            "mapping_only_command": latest_drop_intake["payload"].get("mapping_only_command"),
            "one_shot_command": latest_drop_intake["payload"].get("one_shot_command"),
            "generated_at": latest_drop_intake["payload"].get("generated_at"),
        },
        "latest_final_creative_assets": {
            "exists": latest_final_creative_assets["exists"],
            "dir": latest_final_creative_assets["dir"],
            "manifest": latest_final_creative_assets["manifest"],
            "gate": latest_final_creative_payload.get("gate"),
            "generated_at": latest_final_creative_payload.get("generated_at"),
            "assets_count": len(latest_final_creative_rows),
            "creative_ids": [
                str(row.get("creative_id") or "")
                for row in latest_final_creative_rows
                if isinstance(row, dict)
            ],
            "campaign_shape": latest_final_creative_payload.get("campaign_shape", {}),
            "landing_cta_priority": latest_final_creative_payload.get("landing_cta_priority", []),
            "mapping_path": (
                str(Path(latest_final_creative_assets["dir"]) / "final_creative_asset_mapping_3ads_pending_publish.json")
                if latest_final_creative_assets["dir"]
                else ""
            ),
        },
        "latest_meta_api_primary_preflight": {
            "exists": latest_meta_api_preflight["exists"],
            "dir": latest_meta_api_preflight["dir"],
            "manifest": latest_meta_api_preflight["manifest"],
            "gate": latest_meta_api_preflight["payload"].get("gate"),
            "generated_at": latest_meta_api_preflight["payload"].get(
                "created_at_local"
            ),
            "live_readonly": latest_meta_api_preflight["payload"].get("live_readonly"),
            "env": latest_meta_api_preflight["payload"].get("env", {}),
            "write_gate_without_owner_phrase": latest_meta_api_preflight["payload"].get(
                "write_gate_without_owner_phrase", {}
            ),
            "preflight_command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/preflight_meta_api_primary.py --live-readonly --json"
            ),
        },
        "latest_meta_line31_publish_preflight": {
            "exists": latest_meta_publish_preflight["exists"],
            "dir": latest_meta_publish_preflight["dir"],
            "manifest": latest_meta_publish_preflight["manifest"],
            "gate": latest_meta_publish_payload.get("gate"),
            "created_at_local": latest_meta_publish_payload.get(
                "created_at_local"
            ),
            "mapping": latest_meta_publish_payload.get("mapping", {}),
            "launch_shape": latest_meta_publish_payload.get(
                "launch_shape", {}
            ),
            "errors": latest_meta_publish_payload.get("errors", []),
            "preflight_evidence_lock": latest_meta_publish_payload.get(
                "preflight_evidence_lock", {}
            ),
            "required_meta_write_phrase_present": bool(
                latest_meta_publish_payload.get("required_meta_write_phrase")
            ),
            "required_meta_write_phrase_path": latest_meta_write_phrase_path,
            "write_gate": latest_meta_publish_payload.get(
                "write_gate", {}
            ),
            "apply_requested": latest_meta_publish_payload.get("apply_requested"),
            "meta_write_attempted": latest_meta_publish_payload.get("meta_write_attempted"),
            "apply_result": latest_meta_publish_payload.get("apply_result"),
            "preflight_command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/preflight_line31_countrywide_meta_publish.py --json"
            ),
        },
        "latest_meta_current_readonly_snapshot": {
            "exists": latest_meta_current_readonly_snapshot["exists"],
            "dir": latest_meta_current_readonly_snapshot["dir"],
            "manifest": latest_meta_current_readonly_snapshot["manifest"],
            "gate": latest_meta_current_readonly_snapshot["payload"].get("gate"),
            "generated_at": latest_meta_current_readonly_snapshot["payload"].get(
                "generated_at"
            ),
            "checks_csv": latest_meta_current_readonly_snapshot["payload"].get(
                "checks_csv"
            ),
            "checks_total": latest_meta_current_readonly_snapshot["payload"].get(
                "checks_total"
            ),
            "checks_failed": latest_meta_current_readonly_snapshot["payload"].get(
                "checks_failed"
            ),
            "checks_review": latest_meta_current_readonly_snapshot["payload"].get(
                "checks_review"
            ),
            "current_state_summary": latest_meta_current_readonly_snapshot[
                "payload"
            ].get("current_state_summary", {}),
            "retained_ui_only_gaps": latest_meta_current_readonly_snapshot[
                "payload"
            ].get("retained_ui_only_gaps", []),
            "snapshot_command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/snapshot_line31_current_meta_state.py --json"
            ),
        },
        "latest_meta_current_activation_preflight": {
            "exists": latest_meta_current_activation_preflight["exists"],
            "dir": latest_meta_current_activation_preflight["dir"],
            "manifest": latest_meta_current_activation_preflight["manifest"],
            "gate": latest_activation_payload.get("gate"),
            "created_at_local": latest_activation_payload.get("created_at_local"),
            "preflight_evidence_lock": latest_activation_payload.get(
                "preflight_evidence_lock", {}
            ),
            "required_meta_write_phrase_path": latest_activation_payload.get(
                "required_meta_write_phrase_path", ""
            ),
            "write_gate": latest_activation_payload.get("write_gate", {}),
            "apply_requested": latest_activation_payload.get("apply_requested"),
            "meta_write_attempted": latest_activation_payload.get(
                "meta_write_attempted"
            ),
            "activation_scope": latest_activation_payload.get(
                "activation_scope", {}
            ),
            "preflight_command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/preflight_line31_current_meta_activation.py --json"
            ),
        },
        "latest_meta_launch_identity_discovery": {
            "exists": latest_meta_launch_identity_discovery["exists"],
            "dir": latest_meta_launch_identity_discovery["dir"],
            "manifest": latest_meta_launch_identity_discovery["manifest"],
            "gate": latest_meta_launch_identity_discovery["payload"].get("gate"),
            "created_at_local": latest_meta_launch_identity_discovery["payload"].get(
                "created_at_local"
            ),
            "recommended": latest_meta_launch_identity_discovery["payload"].get(
                "recommended", {}
            ),
            "missing": latest_meta_launch_identity_discovery["payload"].get(
                "missing", []
            ),
            "secondary_lookup_errors": latest_meta_launch_identity_discovery[
                "payload"
            ].get("secondary_lookup_errors", []),
            "instagram_actor_id_optional_evidence": latest_meta_launch_identity_discovery[
                "payload"
            ].get("instagram_actor_id_optional_evidence", {}),
            "recommended_env_lines_path": (
                str(Path(latest_meta_launch_identity_discovery["dir"]) / "recommended_env_lines.txt")
                if latest_meta_launch_identity_discovery["dir"]
                else ""
            ),
            "discovery_command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/discover_meta_launch_identity.py "
                "--live-readonly --json"
            ),
        },
        "latest_web_deploy_approval_packet": {
            "exists": latest_web_deploy_approval["exists"],
            "dir": latest_web_deploy_approval["dir"],
            "manifest": latest_web_deploy_approval["manifest"],
            "gate": latest_web_deploy_approval["payload"].get("gate"),
            "created_at_local": latest_web_deploy_approval["payload"].get(
                "created_at_local"
            ),
            "build_dist_fingerprint_sha256": latest_web_deploy_approval[
                "payload"
            ].get("build_dist_fingerprint_sha256"),
            "deploy_preflight_path": latest_web_deploy_approval["payload"].get(
                "deploy_preflight_path"
            ),
            "exact_owner_deploy_approval_phrase": latest_web_deploy_approval[
                "payload"
            ].get("exact_owner_deploy_approval_phrase")
            or latest_web_deploy_approval["payload"].get(
                "exact_owner_deploy_and_liveqa_approval_phrase"
            ),
            "customer_visible_copy_contract": latest_web_deploy_approval[
                "payload"
            ].get("customer_visible_copy_contract", {}),
            "live_probe_before_deploy": latest_web_deploy_approval[
                "payload"
            ].get("live_probe_before_deploy", {}),
            "paired_meta_preflight": latest_web_deploy_approval["payload"].get(
                "paired_meta_preflight", {}
            ),
            "deploy_command_if_approved": latest_web_deploy_approval["payload"].get(
                "deploy_command_if_approved"
            ),
            "postdeploy_live_qa_command_if_approved": latest_web_deploy_approval[
                "payload"
            ].get("postdeploy_live_qa_command_if_approved"),
            "postdeploy_live_qa_expected_json": latest_web_deploy_approval[
                "payload"
            ].get("postdeploy_live_qa_expected_json"),
            "validation": latest_web_deploy_approval["payload"].get("validation", {}),
        },
        "latest_web_wrangler_dryrun": latest_web_wrangler_dryrun,
        "latest_deploy_liveqa_sequence": {
            "exists": latest_deploy_liveqa_sequence["exists"],
            "dir": latest_deploy_liveqa_sequence["dir"],
            "manifest": latest_deploy_liveqa_sequence["manifest"],
            "gate": latest_deploy_liveqa_sequence["payload"].get("gate"),
            "generated_at": latest_deploy_liveqa_sequence["payload"].get("generated_at"),
            "external_write_attempted": latest_deploy_liveqa_sequence["payload"].get(
                "external_write_attempted"
            ),
            "meta_write_attempted": latest_deploy_liveqa_sequence["payload"].get(
                "meta_write_attempted"
            ),
            "live_route_probe": latest_deploy_liveqa_sequence["payload"].get(
                "live_route_probe", {}
            ),
            "live_qa": latest_deploy_liveqa_sequence["payload"].get("live_qa"),
            "mapping_validation": latest_deploy_liveqa_sequence["payload"].get(
                "mapping_validation"
            ),
            "next_meta_publish_approval_phrase_path": latest_sequence_phrase_path,
            "meta_publish_approval_phrase_present": bool(
                latest_sequence_payload.get("meta_publish_approval_phrase")
            ),
        },
        "latest_meta_publish_bridge": {
            "exists": latest_meta_publish_bridge["exists"],
            "dir": latest_meta_publish_bridge["dir"],
            "manifest": latest_meta_publish_bridge["manifest"],
            "gate": latest_meta_publish_bridge["payload"].get("gate"),
            "generated_at": latest_meta_publish_bridge["payload"].get("generated_at"),
            "required_line31_meta_publish_phrase_copy": latest_meta_publish_bridge[
                "payload"
            ].get("required_line31_meta_publish_phrase_copy"),
            "owner_paste_file": latest_meta_publish_bridge["payload"].get(
                "owner_paste_file"
            ),
            "owner_approval_evidence": latest_meta_publish_bridge["payload"].get(
                "owner_approval_evidence"
            ),
            "owner_approved_mapping": latest_meta_publish_bridge["payload"].get(
                "owner_approved_mapping"
            ),
            "meta_api_live_write_approval_file": latest_meta_publish_bridge[
                "payload"
            ].get("meta_api_live_write_approval_file"),
            "commands": latest_meta_publish_bridge["payload"].get("commands", {}),
            "two_stage_approval_boundary": latest_meta_publish_bridge["payload"].get(
                "two_stage_approval_boundary", []
            ),
            "external_write_attempted": latest_meta_publish_bridge["payload"].get(
                "external_write_attempted"
            ),
            "meta_write_attempted": latest_meta_publish_bridge["payload"].get(
                "meta_write_attempted"
            ),
            "bridge_plan_command": (
                "python3 scripts/plan_line31_meta_publish_bridge.py --json"
            ),
        },
        "latest_post_publish_monitoring_packet": {
            "exists": latest_post_publish_monitoring_packet["exists"],
            "dir": latest_post_publish_monitoring_packet["dir"],
            "manifest": latest_post_publish_monitoring_packet["manifest"],
            "gate": latest_post_publish_monitoring_packet["payload"].get("gate"),
            "generated_at": latest_post_publish_monitoring_packet["payload"].get(
                "generated_at"
            ),
            "commands_tsv": latest_post_publish_monitoring_packet["payload"].get(
                "commands_tsv"
            ),
            "future_synthetic_tracking_qa_approval_phrase_path": latest_post_publish_monitoring_packet[
                "payload"
            ].get("future_synthetic_tracking_qa_approval_phrase_path"),
            "truth_separation_contract": latest_post_publish_monitoring_packet[
                "payload"
            ].get("truth_separation_contract", []),
            "decision_gates": latest_post_publish_monitoring_packet["payload"].get(
                "decision_gates", {}
            ),
            "checks": latest_post_publish_monitoring_packet["payload"].get(
                "checks", {}
            ),
            "external_write_attempted": latest_post_publish_monitoring_packet[
                "payload"
            ].get("external_write_attempted"),
            "meta_write_attempted": latest_post_publish_monitoring_packet[
                "payload"
            ].get("meta_write_attempted"),
            "packet_command": (
                "python3 scripts/build_line31_post_publish_monitoring_packet.py --json"
            ),
        },
        "latest_expert_launch_answer_intake": {
            "exists": latest_expert_launch_answer_intake["exists"],
            "dir": latest_expert_launch_answer_intake["dir"],
            "manifest": latest_expert_launch_answer_intake["manifest"],
            "gate": latest_expert_launch_answer_intake["payload"].get("gate"),
            "generated_at": latest_expert_launch_answer_intake["payload"].get(
                "generated_at"
            ),
            "decision": latest_expert_launch_answer_intake["payload"].get(
                "decision"
            ),
            "decision_confidence": latest_expert_launch_answer_intake[
                "payload"
            ].get("decision_confidence"),
            "answer_dir": latest_expert_launch_answer_intake["payload"].get(
                "answer_dir"
            ),
            "answer_path": latest_expert_launch_answer_intake["payload"].get(
                "answer_path"
            ),
            "next_safe_action": latest_expert_launch_answer_intake["payload"].get(
                "next_safe_action", {}
            ),
            "intake_command": (
                "python3 scripts/ingest_line31_expert_launch_answer.py --json"
            ),
        },
        "latest_post_expert_answer_sequence": {
            "exists": latest_post_expert_answer_sequence["exists"],
            "dir": latest_post_expert_answer_sequence["dir"],
            "manifest": latest_post_expert_answer_sequence["manifest"],
            "gate": latest_post_expert_answer_sequence["payload"].get("gate"),
            "generated_at": latest_post_expert_answer_sequence["payload"].get(
                "generated_at"
            ),
            "oracle_pack": latest_post_expert_answer_sequence["payload"].get(
                "oracle_pack"
            ),
            "expert_intake": latest_post_expert_answer_sequence["payload"].get(
                "expert_intake", {}
            ),
            "current_status": latest_post_expert_answer_sequence["payload"].get(
                "current_status", {}
            ),
            "completion_audit": latest_post_expert_answer_sequence["payload"].get(
                "completion_audit", {}
            ),
            "next_safe_action": latest_post_expert_answer_sequence["payload"].get(
                "next_safe_action", ""
            ),
            "summary_md": latest_post_expert_answer_sequence["payload"].get(
                "summary_md"
            ),
            "next_safe_action_md": latest_post_expert_answer_sequence["payload"].get(
                "next_safe_action_md"
            ),
            "sequence_command": (
                "python3 scripts/run_line31_post_expert_answer_sequence.py --json"
            ),
        },
        "latest_meta_live_write_ready_stopline": {
            "exists": latest_meta_live_write_ready_stopline["exists"],
            "dir": latest_meta_live_write_ready_stopline["dir"],
            "manifest": latest_meta_live_write_ready_stopline["manifest"],
            "gate": latest_meta_live_write_ready_stopline["payload"].get("gate"),
            "created_at": latest_meta_live_write_ready_stopline["payload"].get(
                "created_at"
            ),
            "approval_paste_file": latest_meta_live_write_ready_stopline["payload"].get(
                "approval_paste_file"
            ),
            "owner_approved_mapping": latest_meta_live_write_ready_stopline[
                "payload"
            ].get("owner_approved_mapping", {}),
            "required_live_write_phrase_file": (
                latest_meta_live_write_ready_stopline["payload"]
                .get("meta_preflight", {})
                .get("required_live_write_phrase_file")
            ),
            "required_live_write_phrase_file_sha256": (
                latest_meta_live_write_ready_stopline["payload"]
                .get("meta_preflight", {})
                .get("required_live_write_phrase_file_sha256")
            ),
            "preflight_evidence_lock": (
                latest_meta_live_write_ready_stopline["payload"]
                .get("meta_preflight", {})
                .get("preflight_evidence_lock")
            ),
            "preflight_evidence_lock_sha256": (
                latest_meta_live_write_ready_stopline["payload"]
                .get("meta_preflight", {})
                .get("preflight_evidence_lock_sha256")
            ),
            "apply_command": latest_meta_live_write_ready_stopline["payload"].get(
                "apply_command"
            ),
            "live_apply_expected_gate_after_approval": (
                latest_meta_live_write_ready_stopline["payload"].get(
                    "live_apply_expected_gate_after_approval"
                )
            ),
            "goal_complete": latest_meta_live_write_ready_stopline["payload"].get(
                "goal_complete"
            ),
            "meta_write_attempted": latest_meta_live_write_ready_stopline["payload"].get(
                "meta_write_attempted"
            ),
            "external_write_attempted": latest_meta_live_write_ready_stopline[
                "payload"
            ].get("external_write_attempted"),
        },
        "latest_meta_api_live_partial_blocker": {
            "exists": latest_meta_api_live_partial_blocker["exists"],
            "dir": latest_meta_api_live_partial_blocker["dir"],
            "manifest": latest_meta_api_live_partial_blocker["manifest"],
            "gate": latest_meta_api_live_partial_blocker["payload"].get("gate"),
            "created_at": latest_meta_api_live_partial_blocker["payload"].get(
                "created_at"
            ),
            "campaign": latest_meta_api_live_partial_blocker["payload"].get(
                "campaign", {}
            ),
            "adset": latest_meta_api_live_partial_blocker["payload"].get("adset", {}),
            "approval": latest_meta_api_live_partial_blocker["payload"].get(
                "approval", {}
            ),
            "last_source_backed_exact_ad_count": latest_meta_api_live_partial_blocker[
                "payload"
            ].get("last_source_backed_exact_ad_count"),
            "latest_blocker": latest_meta_api_live_partial_blocker["payload"].get(
                "latest_blocker", {}
            ),
            "post_attempt_verification": latest_meta_api_live_partial_blocker[
                "payload"
            ].get("post_attempt_verification", {}),
            "three_ads_live_verified": latest_meta_api_live_partial_blocker[
                "payload"
            ].get("three_ads_live_verified"),
            "safe_next_options": latest_meta_api_live_partial_blocker["payload"].get(
                "safe_next_options", []
            ),
        },
        "latest_meta_budget_currency_stopline": {
            "exists": latest_meta_budget_currency_stopline["exists"],
            "dir": latest_meta_budget_currency_stopline["dir"],
            "manifest": latest_meta_budget_currency_stopline["manifest"],
            "gate": latest_meta_budget_currency_stopline["payload"].get("gate"),
            "created_at": latest_meta_budget_currency_stopline["payload"].get(
                "created_at"
            ),
            "owner_observation": latest_meta_budget_currency_stopline["payload"].get(
                "owner_observation", {}
            ),
            "approved_intent": latest_meta_budget_currency_stopline["payload"].get(
                "approved_intent", {}
            ),
            "meta_objects": latest_meta_budget_currency_stopline["payload"].get(
                "meta_objects", {}
            ),
            "risk": latest_meta_budget_currency_stopline["payload"].get("risk", {}),
            "safety_pause": latest_meta_budget_currency_stopline["payload"].get(
                "safety_pause", {}
            ),
            "currency_safe_preflight": latest_meta_budget_currency_stopline[
                "payload"
            ].get("currency_safe_preflight", {}),
            "handoff": latest_meta_budget_currency_stopline["payload"].get(
                "handoff", {}
            ),
            "safe_next_options": latest_meta_budget_currency_stopline["payload"].get(
                "safe_next_options", []
            ),
        },
        "latest_meta_partial_shell_safety_pause": {
            "exists": latest_meta_partial_shell_safety_pause["exists"],
            "dir": latest_meta_partial_shell_safety_pause["dir"],
            "manifest": latest_meta_partial_shell_safety_pause["manifest"],
            "gate": latest_meta_partial_shell_safety_pause["payload"].get("gate"),
            "created_at": latest_meta_partial_shell_safety_pause["payload"].get(
                "created_at"
            ),
            "approval_phrase_recorded": latest_meta_partial_shell_safety_pause[
                "payload"
            ].get("approval_phrase_recorded"),
            "scope": latest_meta_partial_shell_safety_pause["payload"].get(
                "scope", {}
            ),
            "before": latest_meta_partial_shell_safety_pause["payload"].get(
                "before", {}
            ),
            "after": latest_meta_partial_shell_safety_pause["payload"].get(
                "after", {}
            ),
            "verification": latest_meta_partial_shell_safety_pause["payload"].get(
                "verification", {}
            ),
            "errors": latest_meta_partial_shell_safety_pause["payload"].get(
                "errors", []
            ),
        },
        "latest_line31_meta_30min_rescue": latest_line31_meta_rescue,
        "latest_customer_journey_traceability_audit": {
            "exists": latest_customer_journey_traceability_audit["exists"],
            "dir": latest_customer_journey_traceability_audit["dir"],
            "manifest": latest_customer_journey_traceability_audit["manifest"],
            "gate": latest_customer_journey_traceability_audit["payload"].get("gate"),
            "generated_at": latest_customer_journey_traceability_audit["payload"].get(
                "generated_at"
            ),
            "checks_csv": latest_customer_journey_traceability_audit["payload"].get(
                "checks_csv"
            ),
            "checks_total": latest_customer_journey_traceability_audit["payload"].get(
                "checks_total"
            ),
            "checks_failed": latest_customer_journey_traceability_audit[
                "payload"
            ].get("checks_failed"),
            "journey_chain": latest_customer_journey_traceability_audit["payload"].get(
                "journey_chain", []
            ),
            "mapping_summary": latest_customer_journey_traceability_audit[
                "payload"
            ].get("mapping_summary", {}),
            "live_qa_summary": latest_customer_journey_traceability_audit[
                "payload"
            ].get("live_qa_summary", {}),
            "external_write_attempted": latest_customer_journey_traceability_audit[
                "payload"
            ].get("external_write_attempted"),
            "meta_write_attempted": latest_customer_journey_traceability_audit[
                "payload"
            ].get("meta_write_attempted"),
            "audit_command": (
                "python3 scripts/build_line31_customer_journey_traceability_audit.py --json"
            ),
        },
        "latest_line31_live_customer_label_probe": {
            "exists": latest_line31_live_customer_label_probe["exists"],
            "dir": latest_line31_live_customer_label_probe["dir"],
            "manifest": latest_line31_live_customer_label_probe["manifest"],
            "gate": latest_line31_live_customer_label_probe["payload"].get("gate"),
            "generated_at": latest_line31_live_customer_label_probe["payload"].get(
                "generated_at"
            ),
            "checks_csv": latest_line31_live_customer_label_probe["payload"].get(
                "checks_csv"
            ),
            "checks_total": latest_line31_live_customer_label_probe["payload"].get(
                "checks_total"
            ),
            "checks_failed": latest_line31_live_customer_label_probe["payload"].get(
                "checks_failed"
            ),
            "summary": latest_line31_live_customer_label_probe["payload"].get(
                "summary", {}
            ),
            "landing_html_sha256": latest_line31_live_customer_label_probe["payload"].get(
                "landing_html_sha256"
            ),
            "probe_command": (
                "python3 scripts/probe_line31_live_customer_label.py --json"
            ),
        },
        "completion_audit_command": (
            "python3 scripts/audit_line31_active_goal_completion.py --json"
        ),
        "safety": {
            "writes_protected_surfaces": False,
            "external_writes": False,
            "purpose": "stable local operator pointer only",
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Launch Current Status",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        f"Status: `{payload['status']}`",
        f"Owner-facing publish status: `{payload['owner_facing_publish_status']}`",
        f"Post-expert integration: `{payload['post_expert_integration_status']}`",
        f"Ready to publish: `{str(payload['ready_to_publish']).lower()}`",
        f"Pending gate: `{payload['pending_gate']}`",
        f"Strict gate: `{payload['strict_gate']}`",
        "",
        "## Next Action",
        "",
        payload["next_action"],
        "",
        "## Latest Evidence",
        "",
        f"- Latest preflight packet: `{payload['latest_preflight_packet']['dir']}`",
        f"- Latest preflight gate: `{payload['latest_preflight_packet']['gate']}`",
        f"- Latest drop-intake folder: `{payload['latest_drop_intake']['dir']}`",
        f"- Latest final-assets folder: `{payload['latest_drop_intake'].get('asset_dir')}`",
        f"- Latest staged multi-creative folder: `{payload['latest_final_creative_assets']['dir']}`",
        f"- Latest staged multi-creative assets: `{payload['latest_final_creative_assets']['assets_count']}`",
        f"- Latest web deploy approval packet: `{payload['latest_web_deploy_approval_packet']['dir']}`",
        f"- Latest web deploy approval gate: `{payload['latest_web_deploy_approval_packet']['gate']}`",
        f"- Latest Wrangler deploy dry-run: `{payload['latest_web_wrangler_dryrun'].get('dir')}`",
        f"- Latest Wrangler deploy dry-run gate: `{payload['latest_web_wrangler_dryrun'].get('gate')}`",
        f"- Latest deploy/live-QA sequence: `{payload['latest_deploy_liveqa_sequence']['dir']}`",
        f"- Latest deploy/live-QA sequence gate: `{payload['latest_deploy_liveqa_sequence']['gate']}`",
        f"- Latest LINE31 Meta approval bridge: `{payload['latest_meta_publish_bridge']['dir']}`",
        f"- Latest LINE31 Meta approval bridge gate: `{payload['latest_meta_publish_bridge']['gate']}`",
        f"- Latest post-publish monitoring packet: `{payload['latest_post_publish_monitoring_packet']['dir']}`",
        f"- Latest post-publish monitoring gate: `{payload['latest_post_publish_monitoring_packet']['gate']}`",
        f"- Latest expert launch-answer intake packet: `{payload['latest_expert_launch_answer_intake']['dir']}`",
        f"- Latest expert launch-answer intake gate: `{payload['latest_expert_launch_answer_intake']['gate']}`",
        f"- Latest post-expert answer sequence packet: `{payload['latest_post_expert_answer_sequence']['dir']}`",
        f"- Latest post-expert answer sequence gate: `{payload['latest_post_expert_answer_sequence']['gate']}`",
        f"- Latest customer journey traceability audit: `{payload['latest_customer_journey_traceability_audit']['dir']}`",
        f"- Latest customer journey traceability gate: `{payload['latest_customer_journey_traceability_audit']['gate']}`",
        f"- Latest LINE31 live customer-label probe: `{payload['latest_line31_live_customer_label_probe']['dir']}`",
        f"- Latest LINE31 live customer-label gate: `{payload['latest_line31_live_customer_label_probe']['gate']}`",
        f"- Latest Meta API primary preflight: `{payload['latest_meta_api_primary_preflight']['dir']}`",
        f"- Latest Meta API preflight gate: `{payload['latest_meta_api_primary_preflight']['gate']}`",
        f"- Latest LINE31 Meta publish preflight: `{payload['latest_meta_line31_publish_preflight']['dir']}`",
        f"- Latest LINE31 Meta publish preflight gate: `{payload['latest_meta_line31_publish_preflight']['gate']}`",
        f"- Latest LINE31 Meta current read-only snapshot: `{payload['latest_meta_current_readonly_snapshot']['dir']}`",
        f"- Latest LINE31 Meta current read-only snapshot gate: `{payload['latest_meta_current_readonly_snapshot']['gate']}`",
        f"- Latest Meta live-write ready stopline: `{payload['latest_meta_live_write_ready_stopline']['dir']}`",
        f"- Latest Meta live-write ready stopline gate: `{payload['latest_meta_live_write_ready_stopline']['gate']}`",
        f"- Latest Meta API partial blocker: `{payload['latest_meta_api_live_partial_blocker']['dir']}`",
        f"- Latest Meta API partial blocker gate: `{payload['latest_meta_api_live_partial_blocker']['gate']}`",
        f"- Latest Meta launch identity discovery: `{payload['latest_meta_launch_identity_discovery']['dir']}`",
        f"- Latest Meta launch identity discovery gate: `{payload['latest_meta_launch_identity_discovery']['gate']}`",
        f"- Latest approval placeholder: `{payload['latest_drop_intake'].get('approval_text_file')}`",
        f"- Latest drop-intake checklist: `{payload['latest_drop_intake'].get('checklist_path')}`",
        "",
        "## Launch-Critical Paths",
        "",
        f"- Final creative mapping: `{payload['mapping_path']}`",
        f"- Owner approval phrase source: `{payload['approval_phrase_path']}`",
        "",
        "## Missing Or Pending",
        "",
    ]
    if payload["missing_or_pending"]:
        lines.extend(f"- `{item}`" for item in payload["missing_or_pending"])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Non-Creative Blockers",
            "",
        ]
    )
    if payload["noncreative_blockers"]:
        lines.extend(f"- {item}" for item in payload["noncreative_blockers"])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Latest Drop-Intake Commands",
            "",
            "Validate the latest intake folder from the stable current pointer first:",
            "",
            "```bash",
            payload["current_drop_validator_command"],
            "```",
            "",
            "Validate the latest intake folder with explicit paths if needed:",
            "",
            "```bash",
            payload["latest_drop_intake"].get("drop_validator_command") or "",
            "```",
            "",
            "Preferred one-shot command for the latest intake folder:",
            "",
            "```bash",
            payload["latest_drop_intake"].get("one_shot_command") or payload[
                "one_shot_example_command"
            ],
            "```",
            "",
            "## Preferred One-Shot Command",
            "",
            "```bash",
            payload["one_shot_example_command"],
            "```",
            "",
            "## Standalone Approval Recorder",
            "",
            payload["approval_evidence_requirement"],
            "",
            "```bash",
            payload["standalone_approval_recorder_example_command"],
            "```",
            "",
            "## Meta API Primary",
            "",
            "Use Graph API through `Business_3/Facebook_ads` first. Chrome/Ads Manager UI is fallback only.",
            "",
            "```bash",
            payload["latest_meta_api_primary_preflight"]["preflight_command"],
            "```",
            "",
            f"- Latest gate: `{payload['latest_meta_api_primary_preflight']['gate']}`",
            f"- ENABLE_META_WRITE env: `{payload['latest_meta_api_primary_preflight'].get('env', {}).get('enable_meta_write_env', '')}`",
            "- `ENABLE_META_WRITE=1` is capability only; exact owner approval is still required for any Meta mutation.",
            "",
            "## Meta Launch Identity Discovery",
            "",
            "Use read-only Meta evidence to discover non-secret IDs needed by publish preflight:",
            "",
            "```bash",
            payload["latest_meta_launch_identity_discovery"]["discovery_command"],
            "```",
            "",
            f"- Latest gate: `{payload['latest_meta_launch_identity_discovery']['gate']}`",
            f"- Latest packet: `{payload['latest_meta_launch_identity_discovery']['dir']}`",
            f"- Suggested env lines: `{payload['latest_meta_launch_identity_discovery']['recommended_env_lines_path']}`",
            f"- Recommended META_PAGE_ID: `{payload['latest_meta_launch_identity_discovery'].get('recommended', {}).get('META_PAGE_ID', '')}`",
            f"- Recommended META_INSTAGRAM_ACTOR_ID: `{payload['latest_meta_launch_identity_discovery'].get('recommended', {}).get('META_INSTAGRAM_ACTOR_ID', '')}`",
            f"- Recommended META_PIXEL_ID: `{payload['latest_meta_launch_identity_discovery'].get('recommended', {}).get('META_PIXEL_ID', '')}`",
            f"- Page-only Instagram actor fallback supported: `{str(payload['latest_meta_launch_identity_discovery'].get('instagram_actor_id_optional_evidence', {}).get('supported', False)).lower()}`",
            f"- Page-only Instagram actor fallback observations: `{payload['latest_meta_launch_identity_discovery'].get('instagram_actor_id_optional_evidence', {}).get('observation_count', 0)}`",
            "",
            "Missing identity fields:",
            "",
        ]
    )
    if payload["latest_meta_launch_identity_discovery"].get("missing"):
        lines.extend(
            f"- `{item}`"
            for item in payload["latest_meta_launch_identity_discovery"]["missing"]
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## LINE31 Meta Publish Preflight",
            "",
            "Build the exact three-ad Graph API payload and final Meta write approval phrase only after the mapping is strict-ready:",
            "",
            "```bash",
            payload["latest_meta_line31_publish_preflight"]["preflight_command"],
            "```",
            "",
            f"- Latest gate: `{payload['latest_meta_line31_publish_preflight']['gate']}`",
            f"- Latest packet: `{payload['latest_meta_line31_publish_preflight']['dir']}`",
            f"- Latest preflight lock: `{payload['latest_meta_line31_publish_preflight'].get('preflight_evidence_lock', {}).get('path', '')}`",
            f"- Required Meta live-write phrase: `{payload['latest_meta_line31_publish_preflight'].get('required_meta_write_phrase_path', '')}`",
            f"- Meta write attempted: `{payload['latest_meta_line31_publish_preflight'].get('meta_write_attempted')}`",
            "",
            "Current LINE31 Meta publish blockers:",
            "",
        ]
    )
    if payload["latest_meta_line31_publish_preflight"].get("errors"):
        lines.extend(
            f"- `{item}`"
            for item in payload["latest_meta_line31_publish_preflight"]["errors"]
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## LINE31 Meta Current Read-Only Snapshot",
            "",
            "This is the current Graph API readback of the actual campaign/adset/ads state. It must be checked before trusting older planned payloads.",
            "",
            "```bash",
            payload["latest_meta_current_readonly_snapshot"]["snapshot_command"],
            "```",
            "",
            f"- Latest packet: `{payload['latest_meta_current_readonly_snapshot']['dir']}`",
            f"- Latest gate: `{payload['latest_meta_current_readonly_snapshot']['gate']}`",
            f"- Checks CSV: `{payload['latest_meta_current_readonly_snapshot'].get('checks_csv')}`",
            f"- Checks failed: `{payload['latest_meta_current_readonly_snapshot'].get('checks_failed')}`",
            f"- Checks requiring UI-only review: `{payload['latest_meta_current_readonly_snapshot'].get('checks_review')}`",
            f"- Current campaign status: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('campaign_status', '')}`",
            f"- Current adset status: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('adset_status', '')}`",
            f"- Current adset daily budget: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('adset_daily_budget', '')}`",
            f"- Current ad count: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('ads_by_adset_count', '')}`",
            f"- Current customer CTA: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('customer_visible_cta', '')}`",
            f"- Current landing URL: `{payload['latest_meta_current_readonly_snapshot'].get('current_state_summary', {}).get('landing_url', '')}`",
            "",
            "Retained UI-only gaps:",
            "",
        ]
    )
    if payload["latest_meta_current_readonly_snapshot"].get("retained_ui_only_gaps"):
        lines.extend(
            f"- `{item}`"
            for item in payload["latest_meta_current_readonly_snapshot"][
                "retained_ui_only_gaps"
            ]
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## LINE31 Meta Activate-Only Preflight",
            "",
            "This is the narrow final-start packet for the already-created paused LINE31 objects. It does not create ads or change budget/targeting/creative.",
            "",
            "```bash",
            payload["latest_meta_current_activation_preflight"]["preflight_command"],
            "```",
            "",
            f"- Latest packet: `{payload['latest_meta_current_activation_preflight']['dir']}`",
            f"- Latest gate: `{payload['latest_meta_current_activation_preflight']['gate']}`",
            f"- Preflight lock: `{payload['latest_meta_current_activation_preflight'].get('preflight_evidence_lock', {}).get('path', '')}`",
            f"- Required activation phrase: `{payload['latest_meta_current_activation_preflight'].get('required_meta_write_phrase_path', '')}`",
            f"- Apply requested: `{payload['latest_meta_current_activation_preflight'].get('apply_requested')}`",
            f"- Meta write attempted: `{payload['latest_meta_current_activation_preflight'].get('meta_write_attempted')}`",
            "",
            "Activation scope:",
            "",
            f"- Campaign ID: `{payload['latest_meta_current_activation_preflight'].get('activation_scope', {}).get('campaign_id', '')}`",
            f"- Adset ID: `{payload['latest_meta_current_activation_preflight'].get('activation_scope', {}).get('adset_id', '')}`",
            f"- Ad IDs: `{', '.join(str(item) for item in payload['latest_meta_current_activation_preflight'].get('activation_scope', {}).get('ad_ids', []))}`",
            f"- Status change: `{payload['latest_meta_current_activation_preflight'].get('activation_scope', {}).get('from_status', '')}` -> `{payload['latest_meta_current_activation_preflight'].get('activation_scope', {}).get('to_status', '')}`",
            "",
            "## LINE31 Expert Launch-Answer Intake",
            "",
            "This classifies the external expert answer into exactly one safe next action: start as-is, change before start, hold paused, or manual review.",
            "",
            "```bash",
            payload["latest_expert_launch_answer_intake"]["intake_command"],
            "```",
            "",
            f"- Latest packet: `{payload['latest_expert_launch_answer_intake']['dir']}`",
            f"- Latest gate: `{payload['latest_expert_launch_answer_intake']['gate']}`",
            f"- Decision: `{payload['latest_expert_launch_answer_intake'].get('decision')}`",
            f"- Confidence: `{payload['latest_expert_launch_answer_intake'].get('decision_confidence')}`",
            f"- Answer dir: `{payload['latest_expert_launch_answer_intake'].get('answer_dir')}`",
            f"- Answer path: `{payload['latest_expert_launch_answer_intake'].get('answer_path')}`",
            f"- Next safe action: `{payload['latest_expert_launch_answer_intake'].get('next_safe_action', {}).get('action', '')}`",
            "",
            "## LINE31 Post-Expert Answer Sequence",
            "",
            "This is the preferred one-command no-write wrapper after the external expert answer lands. It classifies the answer, refreshes current status, refreshes the active-goal completion audit, and writes the next safe action.",
            "",
            "```bash",
            payload["latest_post_expert_answer_sequence"]["sequence_command"],
            "```",
            "",
            f"- Latest packet: `{payload['latest_post_expert_answer_sequence']['dir']}`",
            f"- Latest gate: `{payload['latest_post_expert_answer_sequence']['gate']}`",
            f"- Expert decision: `{payload['latest_post_expert_answer_sequence'].get('expert_intake', {}).get('decision')}`",
            f"- Expert intake gate: `{payload['latest_post_expert_answer_sequence'].get('expert_intake', {}).get('gate')}`",
            f"- Completion audit gate: `{payload['latest_post_expert_answer_sequence'].get('completion_audit', {}).get('gate')}`",
            f"- Completion audit complete: `{payload['latest_post_expert_answer_sequence'].get('completion_audit', {}).get('complete')}`",
            f"- Sequence summary: `{payload['latest_post_expert_answer_sequence'].get('summary_md')}`",
            f"- Sequence next-action file: `{payload['latest_post_expert_answer_sequence'].get('next_safe_action_md')}`",
            "",
            "Sequence next safe action:",
            "",
            payload["latest_post_expert_answer_sequence"].get("next_safe_action")
            or "Sequence not generated yet.",
            "",
            "## LINE31 Meta Live-Write Ready Stopline",
            "",
            "This is the current stop point before any Graph API campaign/adset/ad creation. It exists to make the final approval handoff explicit and audit-friendly.",
            "",
            f"- Stopline packet: `{payload['latest_meta_live_write_ready_stopline']['dir']}`",
            f"- Stopline gate: `{payload['latest_meta_live_write_ready_stopline']['gate']}`",
            f"- Stopline manifest: `{payload['latest_meta_live_write_ready_stopline']['manifest']}`",
            f"- Owner-approved mapping: `{payload['latest_meta_live_write_ready_stopline'].get('owner_approved_mapping', {}).get('path', '')}`",
            f"- Owner-approved mapping SHA256: `{payload['latest_meta_live_write_ready_stopline'].get('owner_approved_mapping', {}).get('sha256', '')}`",
            f"- Preflight evidence lock: `{payload['latest_meta_live_write_ready_stopline'].get('preflight_evidence_lock')}`",
            f"- Preflight evidence lock SHA256: `{payload['latest_meta_live_write_ready_stopline'].get('preflight_evidence_lock_sha256')}`",
            f"- Required exact Meta live-write phrase file: `{payload['latest_meta_live_write_ready_stopline'].get('required_live_write_phrase_file')}`",
            f"- Required exact Meta live-write phrase file SHA256: `{payload['latest_meta_live_write_ready_stopline'].get('required_live_write_phrase_file_sha256')}`",
            f"- Paste exact Meta live-write approval here: `{payload['latest_meta_live_write_ready_stopline'].get('approval_paste_file')}`",
            f"- Expected live-apply gate after exact approval: `{payload['latest_meta_live_write_ready_stopline'].get('live_apply_expected_gate_after_approval')}`",
            f"- Goal complete at this stopline: `{payload['latest_meta_live_write_ready_stopline'].get('goal_complete')}`",
            f"- External write attempted by stopline: `{payload['latest_meta_live_write_ready_stopline'].get('external_write_attempted')}`",
            f"- Meta write attempted by stopline: `{payload['latest_meta_live_write_ready_stopline'].get('meta_write_attempted')}`",
            "",
            "Apply command after exact approval:",
            "",
            "```bash",
            payload["latest_meta_live_write_ready_stopline"].get("apply_command")
            or "",
            "```",
        ]
    )

    lines.extend(
        [
            "",
            "## LINE31 Meta API Partial Launch Blocker",
            "",
            "This section records live Meta API progress that is not yet a completed launch.",
            "",
            f"- Partial blocker packet: `{payload['latest_meta_api_live_partial_blocker']['dir']}`",
            f"- Partial blocker gate: `{payload['latest_meta_api_live_partial_blocker']['gate']}`",
            f"- Campaign: `{payload['latest_meta_api_live_partial_blocker'].get('campaign', {}).get('id', '')}` / `{payload['latest_meta_api_live_partial_blocker'].get('campaign', {}).get('name', '')}`",
            f"- Adset: `{payload['latest_meta_api_live_partial_blocker'].get('adset', {}).get('id', '')}` / `{payload['latest_meta_api_live_partial_blocker'].get('adset', {}).get('name', '')}`",
            f"- Last source-backed exact ad count: `{payload['latest_meta_api_live_partial_blocker'].get('last_source_backed_exact_ad_count')}`",
            f"- Three ads live verified: `{payload['latest_meta_api_live_partial_blocker'].get('three_ads_live_verified')}`",
            f"- Latest blocker: `{payload['latest_meta_api_live_partial_blocker'].get('latest_blocker', {}).get('message', '')}`",
            f"- Post-attempt verification gate: `{payload['latest_meta_api_live_partial_blocker'].get('post_attempt_verification', {}).get('gate', '')}`",
            "",
            "Safe next options:",
            "",
        ]
    )
    if payload["latest_meta_api_live_partial_blocker"].get("safe_next_options"):
        lines.extend(
            f"- {item}"
            for item in payload["latest_meta_api_live_partial_blocker"][
                "safe_next_options"
            ]
        )
    else:
        lines.append("- No partial Meta API blocker packet exists.")

    lines.extend(
        [
            "",
            "## LINE31 Meta Budget Currency Stopline",
            "",
            "This section records the owner-observed Ads Manager budget mismatch.",
            "",
            f"- Budget stopline packet: `{payload['latest_meta_budget_currency_stopline']['dir']}`",
            f"- Budget stopline gate: `{payload['latest_meta_budget_currency_stopline']['gate']}`",
            f"- Observed budget display: `{payload['latest_meta_budget_currency_stopline'].get('owner_observation', {}).get('observed_budget_display', '')}`",
            f"- Approved daily budget intent: `{payload['latest_meta_budget_currency_stopline'].get('approved_intent', {}).get('daily_budget_kzt', '')}` KZT",
            f"- Campaign ID: `{payload['latest_meta_budget_currency_stopline'].get('meta_objects', {}).get('campaign_id', '')}`",
            f"- Adset ID: `{payload['latest_meta_budget_currency_stopline'].get('meta_objects', {}).get('adset_id', '')}`",
            f"- Risk: `{payload['latest_meta_budget_currency_stopline'].get('risk', {}).get('summary', '')}`",
            f"- Safety pause gate: `{payload['latest_meta_budget_currency_stopline'].get('safety_pause', {}).get('gate', '')}`",
            f"- Currency-safe preflight lock: `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('preflight_evidence_lock', '')}`",
            f"- Currency-safe preflight SHA-256: `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('preflight_evidence_lock_sha256', '')}`",
            f"- Planned account-currency budget: `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('daily_budget_account_currency', '')}` `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('account_currency', '')}` / day",
            f"- Planned Meta daily_budget payload: `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('daily_budget_minor_units', '')}` minor units",
            f"- Existing paused adset daily_budget: `{payload['latest_meta_budget_currency_stopline'].get('currency_safe_preflight', {}).get('existing_paused_adset_daily_budget', '')}`",
            f"- Next handoff: `{payload['latest_meta_budget_currency_stopline'].get('handoff', {}).get('path', '')}`",
            "",
            "Safe next options:",
            "",
        ]
    )
    if payload["latest_meta_budget_currency_stopline"].get("safe_next_options"):
        lines.extend(
            f"- {item}"
            for item in payload["latest_meta_budget_currency_stopline"][
                "safe_next_options"
            ]
        )
    else:
        lines.append("- No Meta budget currency stopline exists.")

    lines.extend(
        [
            "",
            "## LINE31 Meta Partial Shell Safety Pause",
            "",
            "This section records whether the partial LINE31 Meta shell was paused after the budget stopline.",
            "",
            f"- Pause packet: `{payload['latest_meta_partial_shell_safety_pause']['dir']}`",
            f"- Pause gate: `{payload['latest_meta_partial_shell_safety_pause']['gate']}`",
            f"- Campaign paused: `{payload['latest_meta_partial_shell_safety_pause'].get('verification', {}).get('campaign_status_paused')}`",
            f"- Adset paused: `{payload['latest_meta_partial_shell_safety_pause'].get('verification', {}).get('adset_status_paused')}`",
            f"- Campaign effective status: `{payload['latest_meta_partial_shell_safety_pause'].get('verification', {}).get('campaign_effective_status', '')}`",
            f"- Adset effective status: `{payload['latest_meta_partial_shell_safety_pause'].get('verification', {}).get('adset_effective_status', '')}`",
            f"- Approval evidence: `{payload['latest_meta_partial_shell_safety_pause'].get('approval_phrase_recorded', '')}`",
            "",
        ]
    )

    lines.extend(
        [
            "",
            "## LINE31 Live Customer Label Probe",
            "",
            "This read-only public-page probe prevents stale pre-deploy label evidence from overriding current live truth.",
            "",
            "```bash",
            payload["latest_line31_live_customer_label_probe"]["probe_command"],
            "```",
            "",
            f"- Latest packet: `{payload['latest_line31_live_customer_label_probe']['dir']}`",
            f"- Latest gate: `{payload['latest_line31_live_customer_label_probe']['gate']}`",
            f"- Checks CSV: `{payload['latest_line31_live_customer_label_probe'].get('checks_csv')}`",
            f"- Checks failed: `{payload['latest_line31_live_customer_label_probe'].get('checks_failed')}`",
            f"- Required label present: `{payload['latest_line31_live_customer_label_probe'].get('summary', {}).get('contains_required_customer_label')}`",
            f"- Forbidden LINE31 label present: `{payload['latest_line31_live_customer_label_probe'].get('summary', {}).get('contains_forbidden_customer_label')}`",
            f"- Raw Kaspi product href present: `{payload['latest_line31_live_customer_label_probe'].get('summary', {}).get('contains_raw_kaspi_product_href')}`",
            f"- Landing HTML SHA-256: `{payload['latest_line31_live_customer_label_probe'].get('landing_html_sha256')}`",
            "",
            "## Website Deploy Approval",
            "",
            "This is retained as historical deploy/preflight evidence. Prefer the live customer-label probe above for current page truth.",
            "",
            f"- Deploy preflight: `{payload['latest_web_deploy_approval_packet']['deploy_preflight_path']}`",
            f"- Build/dist fingerprint: `{payload['latest_web_deploy_approval_packet']['build_dist_fingerprint_sha256']}`",
            f"- Prechange gate: `{payload['latest_web_deploy_approval_packet'].get('validation', {}).get('prechange_gate', '')}`",
            f"- Local LINE31 tracking QA: `{payload['latest_web_deploy_approval_packet'].get('validation', {}).get('local_line31_tracking_qa', '')}`",
            f"- Build validation: `{payload['latest_web_deploy_approval_packet'].get('validation', {}).get('build', '')}`",
            f"- Latest Wrangler dry-run closeout: `{payload['latest_web_wrangler_dryrun'].get('closeout')}`",
            f"- Latest Wrangler dry-run log SHA256: `{payload['latest_web_wrangler_dryrun'].get('log_sha256')}`",
            f"- Latest Wrangler dry-run bundle SHA256: `{payload['latest_web_wrangler_dryrun'].get('bundle_index_sha256')}`",
            "",
            "Exact owner phrase required before website deploy:",
            "",
            "```text",
            payload["latest_web_deploy_approval_packet"].get(
                "exact_owner_deploy_approval_phrase"
            )
            or "",
            "```",
            "",
            "Deploy command if approved:",
            "",
            "```bash",
            payload["latest_web_deploy_approval_packet"].get(
                "deploy_command_if_approved"
            )
            or "",
            "```",
            "",
            "Preferred safe sequence runner after exact deploy/live-QA approval:",
            "",
            "```bash",
            payload["deploy_liveqa_sequence_execute_command"],
            "```",
            "",
            "Plan-only runner, no external writes:",
            "",
            "```bash",
            payload["deploy_liveqa_sequence_plan_command"],
            "```",
            "",
            "Expected post-deploy live QA JSON:",
            "",
            "```text",
            payload["latest_web_deploy_approval_packet"].get(
                "postdeploy_live_qa_expected_json"
            )
            or "",
            "```",
            "",
            "Latest no-write deploy/live-QA sequence evidence:",
            "",
            f"- Sequence packet: `{payload['latest_deploy_liveqa_sequence']['dir']}`",
            f"- Sequence gate: `{payload['latest_deploy_liveqa_sequence']['gate']}`",
            f"- External write attempted: `{payload['latest_deploy_liveqa_sequence'].get('external_write_attempted')}`",
            f"- Meta write attempted: `{payload['latest_deploy_liveqa_sequence'].get('meta_write_attempted')}`",
            f"- Route ready for postdeploy QA: `{bool(payload['latest_deploy_liveqa_sequence'].get('live_route_probe', {}).get('route_ready_for_postdeploy_qa'))}`",
            f"- Next Meta approval phrase: `{payload['latest_deploy_liveqa_sequence'].get('next_meta_publish_approval_phrase_path', '')}`",
            "",
            "## LINE31 Meta Approval Bridge",
            "",
            "Use this no-write bridge after the exact LINE31_COUNTRYWIDE_META_PUBLISH phrase is pasted. It keeps the LINE31 owner-approval evidence step separate from the later Meta API live-write approval.",
            "",
            f"- Bridge packet: `{payload['latest_meta_publish_bridge']['dir']}`",
            f"- Bridge gate: `{payload['latest_meta_publish_bridge']['gate']}`",
            f"- External write attempted: `{payload['latest_meta_publish_bridge'].get('external_write_attempted')}`",
            f"- Meta write attempted: `{payload['latest_meta_publish_bridge'].get('meta_write_attempted')}`",
            f"- Required LINE31 phrase copy: `{payload['latest_meta_publish_bridge'].get('required_line31_meta_publish_phrase_copy')}`",
            f"- Paste LINE31 owner approval here: `{payload['latest_meta_publish_bridge'].get('owner_paste_file')}`",
            f"- Owner approval evidence output: `{payload['latest_meta_publish_bridge'].get('owner_approval_evidence')}`",
            f"- Owner-approved mapping output: `{payload['latest_meta_publish_bridge'].get('owner_approved_mapping')}`",
            f"- Later Meta API live-write approval paste file: `{payload['latest_meta_publish_bridge'].get('meta_api_live_write_approval_file')}`",
            "",
            "Stage boundary:",
            "",
        ]
    )
    if payload["latest_meta_publish_bridge"].get("two_stage_approval_boundary"):
        lines.extend(
            f"- {item}"
            for item in payload["latest_meta_publish_bridge"][
                "two_stage_approval_boundary"
            ]
        )
    else:
        lines.append("- Bridge not generated yet.")
    lines.extend(
        [
            "",
            "Bridge plan command:",
            "",
            "```bash",
            payload["latest_meta_publish_bridge"]["bridge_plan_command"],
            "```",
            "",
            "## Post-Publish Monitoring Packet",
            "",
            "This packet defines how to monitor the customer journey after launch without mixing source truths.",
            "",
            f"- Packet: `{payload['latest_post_publish_monitoring_packet']['dir']}`",
            f"- Gate: `{payload['latest_post_publish_monitoring_packet']['gate']}`",
            f"- Commands TSV: `{payload['latest_post_publish_monitoring_packet'].get('commands_tsv')}`",
            f"- Synthetic tracking QA approval phrase: `{payload['latest_post_publish_monitoring_packet'].get('future_synthetic_tracking_qa_approval_phrase_path')}`",
            f"- External write attempted by packet build: `{payload['latest_post_publish_monitoring_packet'].get('external_write_attempted')}`",
            f"- Meta write attempted by packet build: `{payload['latest_post_publish_monitoring_packet'].get('meta_write_attempted')}`",
            "",
            "Truth separation:",
            "",
        ]
    )
    if payload["latest_post_publish_monitoring_packet"].get(
        "truth_separation_contract"
    ):
        lines.extend(
            f"- {item}"
            for item in payload["latest_post_publish_monitoring_packet"][
                "truth_separation_contract"
            ]
        )
    else:
        lines.append("- Monitoring packet not generated yet.")
    lines.extend(
        [
            "",
            "Decision gates:",
            "",
        ]
    )
    decision_gates = payload["latest_post_publish_monitoring_packet"].get(
        "decision_gates"
    )
    if isinstance(decision_gates, dict) and decision_gates:
        lines.extend(
            f"- `{key}`: {value}" for key, value in sorted(decision_gates.items())
        )
    else:
        lines.append("- Monitoring packet not generated yet.")
    lines.extend(
        [
            "",
            "Packet command:",
            "",
            "```bash",
            payload["latest_post_publish_monitoring_packet"]["packet_command"],
            "```",
            "",
            "## Customer Journey Traceability Audit",
            "",
            "This audit checks the full customer path: Meta ad CTA, UTM landing URL, live `/line31`, `/go/:color`, website events, Kaspi redirect, and post-launch truth separation.",
            "",
            f"- Audit packet: `{payload['latest_customer_journey_traceability_audit']['dir']}`",
            f"- Gate: `{payload['latest_customer_journey_traceability_audit']['gate']}`",
            f"- Checks CSV: `{payload['latest_customer_journey_traceability_audit'].get('checks_csv')}`",
            f"- Checks total: `{payload['latest_customer_journey_traceability_audit'].get('checks_total')}`",
            f"- Checks failed: `{payload['latest_customer_journey_traceability_audit'].get('checks_failed')}`",
            f"- External write attempted by audit: `{payload['latest_customer_journey_traceability_audit'].get('external_write_attempted')}`",
            f"- Meta write attempted by audit: `{payload['latest_customer_journey_traceability_audit'].get('meta_write_attempted')}`",
            "",
            "Journey chain:",
            "",
        ]
    )
    if payload["latest_customer_journey_traceability_audit"].get("journey_chain"):
        lines.extend(
            f"- {item}"
            for item in payload["latest_customer_journey_traceability_audit"][
                "journey_chain"
            ]
        )
    else:
        lines.append("- Traceability audit not generated yet.")
    lines.extend(
        [
            "",
            "Audit command:",
            "",
            "```bash",
            payload["latest_customer_journey_traceability_audit"]["audit_command"],
            "```",
            "",
            "## Completion Audit",
            "",
            "```bash",
            payload["completion_audit_command"],
            "```",
            "",
            "## Internal Kaspi Policy",
            "",
            f"`{payload['internal_kaspi_policy']}`",
            "",
            "## Safety",
            "",
            "This file is a local pointer only. It does not perform DB, workbook, scheduler, source-pointer, Web_automation, Kaspi/API/WebUI/Meta, campaign, price, stock, cash, PO, supplier, or publication writes.",
            "",
        ]
    )
    return "\n".join(lines)


def write_current_status(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    exports_root: Path = DEFAULT_EXPORTS_ROOT,
    meta_exports_root: Path = DEFAULT_META_EXPORTS_ROOT,
    web_reports_root: Path = DEFAULT_WEB_REPORTS_ROOT,
    json_path: Path = DEFAULT_JSON_PATH,
    markdown_path: Path = DEFAULT_MD_PATH,
) -> dict[str, Any]:
    payload = build_current_status(
        evidence_root=evidence_root,
        exports_root=exports_root,
        meta_exports_root=meta_exports_root,
        web_reports_root=web_reports_root,
    )
    _write_json(json_path, payload)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--exports-root", type=Path, default=DEFAULT_EXPORTS_ROOT)
    parser.add_argument("--meta-exports-root", type=Path, default=DEFAULT_META_EXPORTS_ROOT)
    parser.add_argument("--web-reports-root", type=Path, default=DEFAULT_WEB_REPORTS_ROOT)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MD_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = write_current_status(
        evidence_root=args.evidence_root,
        exports_root=args.exports_root,
        meta_exports_root=args.meta_exports_root,
        web_reports_root=args.web_reports_root,
        json_path=args.json_path,
        markdown_path=args.markdown_path,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"LINE31 current status: {payload['status']}")
        print(payload["markdown_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
