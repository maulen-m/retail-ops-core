from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.write_line31_current_launch_status import (
    build_current_status,
    write_current_status,
)


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_current_status_points_to_latest_packet_and_pending_creative(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    meta_exports_root = tmp_path / "meta_exports"
    web_reports_root = tmp_path / "web_reports"
    _write_manifest(
        exports_root
        / "line31_final_launch_preflight_20260601_010101"
        / "line31_launch_preflight_manifest.json",
        {"gate": "OLD", "ready_to_publish": False, "generated_at": "old"},
    )
    _write_manifest(
        exports_root
        / "line31_final_launch_preflight_20260601_020202"
        / "line31_launch_preflight_manifest.json",
        {
            "gate": "GREEN_EXCEPT_CREATIVE",
            "ready_to_publish": False,
            "generated_at": "new",
        },
    )
    _write_manifest(
        exports_root
        / "line31_final_creative_drop_intake_20260601_030303"
        / "line31_final_creative_drop_intake_manifest.json",
        {
            "generated_at": "drop",
            "asset_dir": "/tmp/final_assets",
            "approval_text_file": "/tmp/approval.txt",
            "checklist_path": "/tmp/checklist.json",
            "drop_validator_command": "python3 scripts/validate_line31_final_creative_drop_intake.py --asset-dir /tmp/final_assets --json",
            "mapping_only_command": "python3 scripts/prepare_line31_final_creative_mapping.py --asset-dir /tmp/final_assets",
            "one_shot_command": "python3 scripts/prepare_line31_launch_readiness_from_assets.py --asset-dir /tmp/final_assets --json",
        },
    )
    _write_manifest(
        exports_root
        / "line31_final_creative_assets_20260601_040404"
        / "manifest.json",
        {
            "generated_at": "assets",
            "gate": "LOCAL_FINAL_CREATIVE_ASSETS_STAGED_PENDING_MAPPING_TRACKING_QA_APPROVAL",
            "campaign_shape": {"ad_count": 3},
            "landing_cta_priority": ["starry_black", "espresso_last"],
            "assets": [
                {"creative_id": "line31_cw_a"},
                {"creative_id": "line31_cw_b"},
                {"creative_id": "line31_cw_c"},
            ],
        },
    )
    _write_manifest(
        exports_root
        / "line31_web_deploy_approval_packet_20260603_010101"
        / "deploy_preflight_manifest.json",
        {
            "gate": "GREEN_DEPLOY_APPROVAL_READY_NO_DEPLOY_PERFORMED",
            "created_at_local": "web-deploy",
            "build_dist_fingerprint_sha256": "build-sha",
            "deploy_preflight_path": "/tmp/deploy_preflight_closeout.md",
            "exact_owner_deploy_approval_phrase": "I approve ACMEWEAR_WEB_LINE31_DEPLOY ...",
            "deploy_command_if_approved": "npx wrangler deploy --config tmp/wrangler.no-analytics.jsonc",
            "postdeploy_live_qa_command_if_approved": "node scripts/probe_line31_tracking_qa.mjs --base-url https://acmewear.pro --allow-live-signal-writes",
            "postdeploy_live_qa_expected_json": "/tmp/line31_tracking_redirect_qa.json",
        },
    )
    _write_manifest(
        exports_root
        / "line31_deploy_liveqa_readiness_sequence_20260603_line31_route_fixed_no_write_v2"
        / "sequence_manifest.json",
        {"gate": "OLD_SEQUENCE_LEXICOGRAPHICALLY_LATE", "generated_at": "old-seq"},
    )
    old_sequence_manifest = (
        exports_root
        / "line31_deploy_liveqa_readiness_sequence_20260603_line31_route_fixed_no_write_v2"
        / "sequence_manifest.json"
    )
    _write_manifest(
        exports_root
        / "line31_deploy_liveqa_readiness_sequence_20260603_060606"
        / "sequence_manifest.json",
        {"gate": "NEW_SEQUENCE_BY_MTIME", "generated_at": "new-seq"},
    )
    new_sequence_manifest = (
        exports_root
        / "line31_deploy_liveqa_readiness_sequence_20260603_060606"
        / "sequence_manifest.json"
    )
    os.utime(old_sequence_manifest, (1_700_000_000, 1_700_000_000))
    os.utime(new_sequence_manifest, (1_800_000_000, 1_800_000_000))
    _write_manifest(
        exports_root
        / "line31_meta_publish_bridge_20260603_070707"
        / "bridge_manifest.json",
        {
            "gate": "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE",
            "generated_at": "bridge",
            "required_line31_meta_publish_phrase_copy": "/tmp/required_phrase.txt",
            "owner_paste_file": "/tmp/owner_line31_approval.txt",
            "owner_approval_evidence": "/tmp/owner_evidence.md",
            "owner_approved_mapping": "/tmp/owner_mapping.json",
            "meta_api_live_write_approval_file": "/tmp/meta_live_write_approval.txt",
            "external_write_attempted": False,
            "meta_write_attempted": False,
            "two_stage_approval_boundary": [
                "Stage 1 records LINE31 approval.",
                "Stage 2 generates Meta API live-write phrase.",
            ],
            "commands": {
                "green_meta_publish_preflight_no_write": "preflight --json",
            },
        },
    )
    _write_manifest(
        exports_root
        / "line31_post_publish_monitoring_packet_20260603_080808"
        / "post_publish_monitoring_manifest.json",
        {
            "gate": "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE",
            "generated_at": "monitoring",
            "commands_tsv": "/tmp/commands.tsv",
            "future_synthetic_tracking_qa_approval_phrase_path": "/tmp/synthetic_phrase.txt",
            "external_write_attempted": False,
            "meta_write_attempted": False,
            "truth_separation_contract": [
                "Meta traffic truth: impressions only.",
                "Kaspi order truth: real orders only.",
            ],
            "decision_gates": {
                "first_hour": "first hour gate",
                "same_day": "same day gate",
                "next_morning": "next morning gate",
            },
            "checks": {"meta_publish_bridge_green": True},
        },
    )
    _write_manifest(
        exports_root
        / "line31_customer_journey_traceability_audit_20260603_090909"
        / "traceability_manifest.json",
        {
            "gate": "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE",
            "generated_at": "traceability",
            "checks_csv": "/tmp/checks.csv",
            "checks_total": 107,
            "checks_failed": 0,
            "external_write_attempted": False,
            "meta_write_attempted": False,
            "journey_chain": [
                "Meta ad CTA uses final 3 creative mapping.",
                "Kaspi order truth remains separate from website click truth.",
            ],
            "mapping_summary": {"assets": []},
            "live_qa_summary": {"browser_events": ["HighIntentKaspiClick"]},
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_api_primary_preflight_20260603_010101"
        / "manifest.json",
        {
            "created_at_local": "meta-old",
            "gate": "OLD",
            "live_readonly": True,
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_api_primary_preflight_20260603_020202"
        / "manifest.json",
        {
            "created_at_local": "meta-new",
            "gate": "GREEN_META_API_PRIMARY_LIVE_READONLY_READY",
            "live_readonly": True,
            "env": {"enable_meta_write_env": "1"},
            "write_gate_without_owner_phrase": {
                "ok": False,
                "reasons": ["owner approval text is empty"],
            },
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_api_primary_preflight_20260603_030303"
        / "manifest.json",
        {
            "created_at_local": "meta-newer-dry-run",
            "gate": "GREEN_META_API_PRIMARY_DRY_RUN_READY",
            "live_readonly": False,
        },
    )
    _write_manifest(
        meta_exports_root
        / "line31_meta_publish_preflight_20260603_040404"
        / "manifest.json",
        {
            "created_at_local": "line31-meta-publish",
            "gate": "YELLOW_META_LINE31_PUBLISH_PREFLIGHT_BLOCKED_NO_WRITE",
            "mapping": {"path": "/tmp/mapping.json", "sha256": "map-sha"},
            "launch_shape": {"daily_budget_kzt": 15000, "hard_cap_kzt": 20000},
            "errors": ["META_PAGE_ID is required for ad creative object_story_spec"],
            "preflight_evidence_lock": {"path": "/tmp/preflight_evidence_lock.json"},
            "write_gate": {"ok": False},
        },
    )
    _write_manifest(
        meta_exports_root
        / "line31_meta_current_readonly_api_snapshot_20260604_100600"
        / "manifest.json",
        {
            "gate": "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_WITH_UI_ONLY_REVIEW_NO_WRITE",
            "generated_at": "snapshot",
            "checks_csv": "/tmp/current_meta_checks.csv",
            "checks_total": 47,
            "checks_failed": 0,
            "checks_review": 1,
            "current_state_summary": {
                "campaign_status": "PAUSED",
                "adset_status": "PAUSED",
                "adset_daily_budget": "3093",
                "ads_by_adset_count": 3,
                "customer_visible_cta": "ORDER_NOW",
                "landing_url": "https://acmewear.pro/line31",
            },
            "retained_ui_only_gaps": [
                "multi_advertiser_ads_off_not_verified_by_graph_api"
            ],
            "external_write_attempted": False,
            "meta_write_attempted": False,
        },
    )
    _write_manifest(
        exports_root
        / "line31_live_customer_label_probe_20260604_100700"
        / "manifest.json",
        {
            "gate": "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE",
            "generated_at": "label",
            "checks_csv": "/tmp/live_label_checks.csv",
            "checks_total": 8,
            "checks_failed": 0,
            "summary": {
                "contains_required_customer_label": True,
                "contains_forbidden_customer_label": False,
                "contains_raw_kaspi_product_href": False,
            },
            "landing_html_sha256": "label-sha",
        },
    )
    _write_manifest(
        exports_root
        / "line31_post_expert_answer_sequence_20260604_113955"
        / "post_expert_answer_sequence_manifest.json",
        {
            "gate": "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE",
            "generated_at": "post-expert-seq",
            "oracle_pack": "/tmp/oracle_pack",
            "expert_intake": {
                "gate": "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE",
                "decision": "PENDING_ANSWER",
            },
            "current_status": {
                "status": "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED",
                "owner_facing_publish_status": "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION",
            },
            "completion_audit": {
                "gate": "INCOMPLETE",
                "complete": False,
            },
            "next_safe_action": "Send the Oracle pack to the external expert.",
            "summary_md": "/tmp/post_expert_summary.md",
            "next_safe_action_md": "/tmp/post_expert_next.md",
            "external_write_attempted": False,
            "meta_write_attempted": False,
        },
    )
    _write_manifest(
        exports_root
        / "line31_meta_live_write_ready_stopline_20260603_041500"
        / "manifest.json",
        {
            "gate": "GREEN_READY_FOR_EXACT_META_API_LIVE_WRITE_APPROVAL_NO_WRITE",
            "created_at": "stopline",
            "approval_paste_file": "/tmp/meta_live_write_approval.txt",
            "owner_approved_mapping": {
                "path": "/tmp/owner_mapping.json",
                "sha256": "owner-map-sha",
            },
            "meta_preflight": {
                "preflight_evidence_lock": "/tmp/preflight_evidence_lock.json",
                "preflight_evidence_lock_sha256": "lock-sha",
                "required_live_write_phrase_file": "/tmp/required_meta_live_write_phrase.txt",
                "required_live_write_phrase_file_sha256": "phrase-sha",
            },
            "apply_command": "python3 scripts/preflight_line31_countrywide_meta_publish.py --execute-approved-meta-publish --json",
            "live_apply_expected_gate_after_approval": "GREEN_META_LINE31_PUBLISH_APPLIED_VERIFY_REQUIRED",
            "goal_complete": False,
            "external_write_attempted": False,
            "meta_write_attempted": False,
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_launch_identity_discovery_20260603_050505"
        / "identity_discovery_manifest.json",
        {
            "created_at_local": "identity",
            "gate": "YELLOW_META_LAUNCH_IDENTITY_INCOMPLETE_NO_WRITE",
            "recommended": {
                "META_PAGE_ID": "page-1",
                "META_INSTAGRAM_ACTOR_ID": "",
                "META_PIXEL_ID": "pixel-1",
            },
            "missing": ["META_INSTAGRAM_ACTOR_ID"],
            "instagram_actor_id_optional_evidence": {
                "supported": True,
                "observation_count": 28,
            },
            "secondary_lookup_errors": [
                {"source": "page_instagram_accounts", "error": "missing pages_read_engagement"}
            ],
        },
    )
    dryrun_dir = web_reports_root / "line31_wrangler_dryrun_20260603_060606"
    dryrun_dir.mkdir(parents=True)
    (dryrun_dir / "closeout.md").write_text(
        "Gate: GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY\n",
        encoding="utf-8",
    )
    (dryrun_dir / "wrangler_dryrun.log").write_text("--dry-run: exiting now.\n", encoding="utf-8")
    (dryrun_dir / "bundle").mkdir()
    (dryrun_dir / "bundle" / "index.js").write_text("export default {};\n", encoding="utf-8")

    payload = build_current_status(
        exports_root=exports_root,
        meta_exports_root=meta_exports_root,
        web_reports_root=web_reports_root,
    )

    assert payload["status"] == "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
    assert payload["ready_to_publish"] is False
    assert payload["owner_facing_publish_status"] == (
        "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION"
    )
    assert payload["noncreative_blockers"] == []
    assert (
        "LINE31 Meta campaign, ad set, and exactly three ads are source-verified but still PAUSED"
        in payload["missing_or_pending"]
    )
    assert not any("three LINE31 Meta ads are not live/source-verified" in item for item in payload["missing_or_pending"])
    assert payload["latest_preflight_packet"]["gate"] == "GREEN_EXCEPT_CREATIVE"
    assert "20260601_020202" in payload["latest_preflight_packet"]["dir"]
    assert "20260601_030303" in payload["latest_drop_intake"]["dir"]
    assert payload["latest_drop_intake"]["asset_dir"] == "/tmp/final_assets"
    assert payload["latest_drop_intake"]["approval_text_file"] == "/tmp/approval.txt"
    assert payload["latest_drop_intake"]["checklist_path"] == "/tmp/checklist.json"
    assert payload["latest_final_creative_assets"]["assets_count"] == 3
    assert payload["latest_final_creative_assets"]["creative_ids"] == [
        "line31_cw_a",
        "line31_cw_b",
        "line31_cw_c",
    ]
    assert payload["latest_final_creative_assets"]["campaign_shape"]["ad_count"] == 3
    assert payload["latest_web_deploy_approval_packet"]["gate"] == (
        "GREEN_DEPLOY_APPROVAL_READY_NO_DEPLOY_PERFORMED"
    )
    assert payload["latest_web_deploy_approval_packet"][
        "build_dist_fingerprint_sha256"
    ] == "build-sha"
    assert payload["latest_web_deploy_approval_packet"][
        "deploy_preflight_path"
    ] == "/tmp/deploy_preflight_closeout.md"
    assert payload["latest_web_deploy_approval_packet"][
        "exact_owner_deploy_approval_phrase"
    ].startswith("I approve ACMEWEAR_WEB_LINE31_DEPLOY")
    assert payload["latest_web_deploy_approval_packet"][
        "postdeploy_live_qa_expected_json"
    ] == "/tmp/line31_tracking_redirect_qa.json"
    assert payload["latest_deploy_liveqa_sequence"]["gate"] == "NEW_SEQUENCE_BY_MTIME"
    assert "20260603_060606" in payload["latest_deploy_liveqa_sequence"]["dir"]
    assert payload["latest_web_wrangler_dryrun"]["gate"] == (
        "GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY"
    )
    assert "20260603_060606" in payload["latest_web_wrangler_dryrun"]["dir"]
    assert payload["latest_web_wrangler_dryrun"]["log_sha256"]
    assert payload["latest_web_wrangler_dryrun"]["bundle_index_sha256"]
    assert payload["latest_meta_publish_bridge"]["gate"] == (
        "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE"
    )
    assert "20260603_070707" in payload["latest_meta_publish_bridge"]["dir"]
    assert payload["latest_meta_publish_bridge"][
        "owner_paste_file"
    ] == "/tmp/owner_line31_approval.txt"
    assert payload["latest_meta_publish_bridge"][
        "meta_api_live_write_approval_file"
    ] == "/tmp/meta_live_write_approval.txt"
    assert payload["latest_meta_publish_bridge"]["meta_write_attempted"] is False
    assert "Stage 1" in payload["latest_meta_publish_bridge"][
        "two_stage_approval_boundary"
    ][0]
    assert payload["latest_post_publish_monitoring_packet"]["gate"] == (
        "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
    )
    assert "20260603_080808" in payload["latest_post_publish_monitoring_packet"]["dir"]
    assert payload["latest_post_publish_monitoring_packet"][
        "commands_tsv"
    ] == "/tmp/commands.tsv"
    assert payload["latest_post_publish_monitoring_packet"][
        "future_synthetic_tracking_qa_approval_phrase_path"
    ] == "/tmp/synthetic_phrase.txt"
    assert payload["latest_post_publish_monitoring_packet"]["meta_write_attempted"] is False
    assert payload["latest_post_publish_monitoring_packet"]["decision_gates"][
        "same_day"
    ] == "same day gate"
    assert payload["latest_customer_journey_traceability_audit"]["gate"] == (
        "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
    )
    assert "20260603_090909" in payload["latest_customer_journey_traceability_audit"]["dir"]
    assert payload["latest_customer_journey_traceability_audit"][
        "checks_csv"
    ] == "/tmp/checks.csv"
    assert payload["latest_customer_journey_traceability_audit"]["checks_total"] == 107
    assert payload["latest_customer_journey_traceability_audit"]["checks_failed"] == 0
    assert payload["latest_customer_journey_traceability_audit"]["meta_write_attempted"] is False
    assert payload["latest_post_expert_answer_sequence"]["gate"] == (
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE"
    )
    assert "20260604_113955" in payload["latest_post_expert_answer_sequence"]["dir"]
    assert payload["latest_post_expert_answer_sequence"]["expert_intake"][
        "decision"
    ] == "PENDING_ANSWER"
    assert payload["latest_post_expert_answer_sequence"]["next_safe_action"] == (
        "Send the Oracle pack to the external expert."
    )
    assert payload["latest_post_expert_answer_sequence"]["sequence_command"] == (
        "python3 scripts/run_line31_post_expert_answer_sequence.py --json"
    )
    assert "run_line31_deploy_liveqa_readiness_sequence.py" in payload[
        "deploy_liveqa_sequence_plan_command"
    ]
    assert "--execute-approved-deploy-liveqa" in payload[
        "deploy_liveqa_sequence_execute_command"
    ]
    assert payload["latest_meta_api_primary_preflight"]["gate"] == (
        "GREEN_META_API_PRIMARY_LIVE_READONLY_READY"
    )
    assert "20260603_020202" in payload["latest_meta_api_primary_preflight"]["dir"]
    assert payload["latest_meta_api_primary_preflight"]["env"]["enable_meta_write_env"] == "1"
    assert payload["latest_meta_api_primary_preflight"][
        "write_gate_without_owner_phrase"
    ]["ok"] is False
    assert payload["latest_meta_line31_publish_preflight"]["gate"] == (
        "YELLOW_META_LINE31_PUBLISH_PREFLIGHT_BLOCKED_NO_WRITE"
    )
    assert "20260603_040404" in payload["latest_meta_line31_publish_preflight"]["dir"]
    assert payload["latest_meta_line31_publish_preflight"]["errors"] == [
        "META_PAGE_ID is required for ad creative object_story_spec"
    ]
    assert payload["latest_meta_line31_publish_preflight"][
        "preflight_evidence_lock"
    ]["path"] == "/tmp/preflight_evidence_lock.json"
    assert payload["latest_meta_current_readonly_snapshot"]["gate"] == (
        "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_WITH_UI_ONLY_REVIEW_NO_WRITE"
    )
    assert "20260604_100600" in payload["latest_meta_current_readonly_snapshot"]["dir"]
    assert payload["latest_meta_current_readonly_snapshot"]["checks_failed"] == 0
    assert payload["latest_meta_current_readonly_snapshot"]["checks_review"] == 1
    assert payload["latest_meta_current_readonly_snapshot"]["current_state_summary"][
        "customer_visible_cta"
    ] == "ORDER_NOW"
    assert payload["latest_meta_current_readonly_snapshot"]["retained_ui_only_gaps"] == [
        "multi_advertiser_ads_off_not_verified_by_graph_api"
    ]
    assert payload["latest_line31_live_customer_label_probe"]["gate"] == (
        "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
    )
    assert payload["latest_line31_live_customer_label_probe"]["checks_failed"] == 0
    assert payload["latest_line31_live_customer_label_probe"]["summary"][
        "contains_required_customer_label"
    ] is True
    assert payload["latest_meta_live_write_ready_stopline"]["gate"] == (
        "GREEN_READY_FOR_EXACT_META_API_LIVE_WRITE_APPROVAL_NO_WRITE"
    )
    assert "20260603_041500" in payload["latest_meta_live_write_ready_stopline"]["dir"]
    assert payload["latest_meta_live_write_ready_stopline"][
        "owner_approved_mapping"
    ]["sha256"] == "owner-map-sha"
    assert payload["latest_meta_live_write_ready_stopline"][
        "preflight_evidence_lock_sha256"
    ] == "lock-sha"
    assert payload["latest_meta_live_write_ready_stopline"][
        "required_live_write_phrase_file_sha256"
    ] == "phrase-sha"
    assert payload["latest_meta_live_write_ready_stopline"]["goal_complete"] is False
    assert payload["latest_meta_live_write_ready_stopline"]["meta_write_attempted"] is False
    assert "--execute-approved-meta-publish" in payload[
        "latest_meta_live_write_ready_stopline"
    ]["apply_command"]
    assert payload["latest_meta_launch_identity_discovery"]["gate"] == (
        "YELLOW_META_LAUNCH_IDENTITY_INCOMPLETE_NO_WRITE"
    )
    assert "20260603_050505" in payload["latest_meta_launch_identity_discovery"]["dir"]
    assert payload["latest_meta_launch_identity_discovery"]["recommended"][
        "META_PAGE_ID"
    ] == "page-1"
    assert payload["latest_meta_launch_identity_discovery"]["missing"] == [
        "META_INSTAGRAM_ACTOR_ID"
    ]
    assert payload["latest_meta_launch_identity_discovery"][
        "instagram_actor_id_optional_evidence"
    ]["supported"] is True
    assert "validate_line31_final_creative_drop_intake.py" in payload["latest_drop_intake"][
        "drop_validator_command"
    ]
    assert payload["current_drop_validator_command"] == (
        "python3 scripts/validate_line31_current_final_creative_drop.py --json"
    )
    assert "prepare_line31_launch_readiness_from_assets.py" in payload["latest_drop_intake"][
        "one_shot_command"
    ]
    assert payload["mapping_path"].endswith("final_creative_asset_mapping_template.json")
    assert payload["approval_phrase_path"].endswith(
        "final_creative_publish_intake_and_approval.md"
    )
    assert payload["safety"]["external_writes"] is False


def test_write_current_status_creates_json_and_markdown(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    meta_exports_root = tmp_path / "meta_exports"
    web_reports_root = tmp_path / "web_reports"
    _write_manifest(
        exports_root
        / "line31_final_launch_preflight_20260601_020202"
        / "line31_launch_preflight_manifest.json",
        {"gate": "GREEN_EXCEPT_CREATIVE", "ready_to_publish": False},
    )
    _write_manifest(
        exports_root
        / "line31_web_deploy_approval_packet_20260603_010101"
        / "deploy_preflight_manifest.json",
        {
            "gate": "GREEN_DEPLOY_APPROVAL_READY_NO_DEPLOY_PERFORMED",
            "build_dist_fingerprint_sha256": "build-sha",
            "deploy_preflight_path": "/tmp/deploy_preflight_closeout.md",
            "exact_owner_deploy_approval_phrase": "I approve ACMEWEAR_WEB_LINE31_DEPLOY ...",
            "deploy_command_if_approved": "npx wrangler deploy --config tmp/wrangler.no-analytics.jsonc",
            "postdeploy_live_qa_expected_json": "/tmp/line31_tracking_redirect_qa.json",
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_api_primary_preflight_20260603_020202"
        / "manifest.json",
        {"gate": "GREEN_META_API_PRIMARY_LIVE_READONLY_READY", "env": {"enable_meta_write_env": "1"}},
    )
    _write_manifest(
        meta_exports_root
        / "line31_meta_publish_preflight_20260603_040404"
        / "manifest.json",
        {
            "gate": "YELLOW_META_LINE31_PUBLISH_PREFLIGHT_BLOCKED_NO_WRITE",
            "errors": ["META_PIXEL_ID is required for Landing Page Views optimization"],
            "preflight_evidence_lock": {"path": "/tmp/meta_publish_lock.json"},
        },
    )
    _write_manifest(
        meta_exports_root
        / "line31_meta_current_readonly_api_snapshot_20260604_100600"
        / "manifest.json",
        {
            "gate": "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_WITH_UI_ONLY_REVIEW_NO_WRITE",
            "checks_csv": "/tmp/current_meta_checks.csv",
            "checks_failed": 0,
            "checks_review": 1,
            "current_state_summary": {
                "campaign_status": "PAUSED",
                "adset_status": "PAUSED",
                "adset_daily_budget": "3093",
                "ads_by_adset_count": 3,
                "customer_visible_cta": "ORDER_NOW",
                "landing_url": "https://acmewear.pro/line31",
            },
            "retained_ui_only_gaps": [
                "multi_advertiser_ads_off_not_verified_by_graph_api"
            ],
        },
    )
    _write_manifest(
        exports_root
        / "line31_live_customer_label_probe_20260604_100700"
        / "manifest.json",
        {
            "gate": "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE",
            "checks_csv": "/tmp/live_label_checks.csv",
            "checks_total": 8,
            "checks_failed": 0,
            "summary": {
                "contains_required_customer_label": True,
                "contains_forbidden_customer_label": False,
                "contains_raw_kaspi_product_href": False,
            },
            "landing_html_sha256": "label-sha",
        },
    )
    _write_manifest(
        exports_root
        / "line31_post_expert_answer_sequence_20260604_113955"
        / "post_expert_answer_sequence_manifest.json",
        {
            "gate": "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE",
            "generated_at": "post-expert-seq",
            "expert_intake": {
                "gate": "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE",
                "decision": "PENDING_ANSWER",
            },
            "completion_audit": {
                "gate": "INCOMPLETE",
                "complete": False,
            },
            "next_safe_action": "Send the Oracle pack to the external expert.",
            "summary_md": "/tmp/post_expert_summary.md",
            "next_safe_action_md": "/tmp/post_expert_next.md",
            "external_write_attempted": False,
            "meta_write_attempted": False,
        },
    )
    _write_manifest(
        exports_root
        / "line31_meta_live_write_ready_stopline_20260603_041500"
        / "manifest.json",
        {
            "gate": "GREEN_READY_FOR_EXACT_META_API_LIVE_WRITE_APPROVAL_NO_WRITE",
            "approval_paste_file": "/tmp/meta_live_write_approval.txt",
            "owner_approved_mapping": {
                "path": "/tmp/owner_mapping.json",
                "sha256": "owner-map-sha",
            },
            "meta_preflight": {
                "preflight_evidence_lock": "/tmp/meta_publish_lock.json",
                "preflight_evidence_lock_sha256": "lock-sha",
                "required_live_write_phrase_file": "/tmp/required_meta_live_write_phrase.txt",
                "required_live_write_phrase_file_sha256": "phrase-sha",
            },
            "apply_command": "python3 scripts/preflight_line31_countrywide_meta_publish.py --execute-approved-meta-publish --json",
            "live_apply_expected_gate_after_approval": "GREEN_META_LINE31_PUBLISH_APPLIED_VERIFY_REQUIRED",
            "goal_complete": False,
            "external_write_attempted": False,
            "meta_write_attempted": False,
        },
    )
    _write_manifest(
        meta_exports_root
        / "meta_launch_identity_discovery_20260603_050505"
        / "identity_discovery_manifest.json",
        {
            "gate": "YELLOW_META_LAUNCH_IDENTITY_INCOMPLETE_NO_WRITE",
            "recommended": {
                "META_PAGE_ID": "page-1",
                "META_INSTAGRAM_ACTOR_ID": "",
                "META_PIXEL_ID": "pixel-1",
            },
            "missing": ["META_INSTAGRAM_ACTOR_ID"],
            "instagram_actor_id_optional_evidence": {
                "supported": True,
                "observation_count": 28,
            },
        },
    )
    dryrun_dir = web_reports_root / "line31_wrangler_dryrun_20260603_060606"
    dryrun_dir.mkdir(parents=True)
    (dryrun_dir / "closeout.md").write_text(
        "Gate: GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY\n",
        encoding="utf-8",
    )
    (dryrun_dir / "wrangler_dryrun.log").write_text("--dry-run: exiting now.\n", encoding="utf-8")
    (dryrun_dir / "bundle").mkdir()
    (dryrun_dir / "bundle" / "index.js").write_text("export default {};\n", encoding="utf-8")
    json_path = tmp_path / "current.json"
    md_path = tmp_path / "current.md"

    payload = write_current_status(
        exports_root=exports_root,
        meta_exports_root=meta_exports_root,
        web_reports_root=web_reports_root,
        json_path=json_path,
        markdown_path=md_path,
    )

    assert payload["json_path"] == str(json_path)
    assert payload["markdown_path"] == str(md_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == (
        "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
    )
    markdown = md_path.read_text(encoding="utf-8")
    assert "# LINE31 Launch Current Status" in markdown
    assert "Ready to publish: `false`" in markdown
    assert "Launch-Critical Paths" in markdown
    assert "Latest final-assets folder" in markdown
    assert "Latest staged multi-creative folder" in markdown
    assert "Latest staged multi-creative assets" in markdown
    assert "Latest web deploy approval packet" in markdown
    assert "Latest Wrangler deploy dry-run" in markdown
    assert "Latest Wrangler dry-run closeout" in markdown
    assert "Latest LINE31 Meta approval bridge" in markdown
    assert "LINE31 Meta Approval Bridge" in markdown
    assert "Bridge not generated yet." in markdown
    assert "Latest post-publish monitoring packet" in markdown
    assert "Post-Publish Monitoring Packet" in markdown
    assert "Monitoring packet not generated yet." in markdown
    assert "Latest post-expert answer sequence packet" in markdown
    assert "Latest post-expert answer sequence gate" in markdown
    assert "Latest customer journey traceability audit" in markdown
    assert "Customer Journey Traceability Audit" in markdown
    assert "Traceability audit not generated yet." in markdown
    assert "Latest LINE31 live customer-label probe" in markdown
    assert "LINE31 Live Customer Label Probe" in markdown
    assert "/tmp/live_label_checks.csv" in markdown
    assert "label-sha" in markdown
    assert "Website Deploy Approval" in markdown
    assert "I approve ACMEWEAR_WEB_LINE31_DEPLOY" in markdown
    assert "Preferred safe sequence runner" in markdown
    assert "run_line31_deploy_liveqa_readiness_sequence.py" in markdown
    assert "/tmp/line31_tracking_redirect_qa.json" in markdown
    assert "Latest Meta API primary preflight" in markdown
    assert "Latest LINE31 Meta publish preflight" in markdown
    assert "Latest LINE31 Meta current read-only snapshot" in markdown
    assert "LINE31 Meta Current Read-Only Snapshot" in markdown
    assert "snapshot_line31_current_meta_state.py --json" in markdown
    assert "/tmp/current_meta_checks.csv" in markdown
    assert "multi_advertiser_ads_off_not_verified_by_graph_api" in markdown
    assert "ORDER_NOW" in markdown
    assert "Latest Meta live-write ready stopline" in markdown
    assert "Meta API Primary" in markdown
    assert "preflight_meta_api_primary.py --live-readonly --json" in markdown
    assert "LINE31 Meta Publish Preflight" in markdown
    assert "preflight_line31_countrywide_meta_publish.py --json" in markdown
    assert "META_PIXEL_ID is required for Landing Page Views optimization" in markdown
    assert "LINE31 Meta Live-Write Ready Stopline" in markdown
    assert "/tmp/meta_live_write_approval.txt" in markdown
    assert "/tmp/required_meta_live_write_phrase.txt" in markdown
    assert "GREEN_META_LINE31_PUBLISH_APPLIED_VERIFY_REQUIRED" in markdown
    assert "--execute-approved-meta-publish" in markdown
    assert "Meta Launch Identity Discovery" in markdown
    assert "discover_meta_launch_identity.py --live-readonly --json" in markdown
    assert "Recommended META_PAGE_ID: `page-1`" in markdown
    assert "Page-only Instagram actor fallback supported: `true`" in markdown
    assert "Page-only Instagram actor fallback observations: `28`" in markdown
    assert "META_INSTAGRAM_ACTOR_ID" in markdown
    assert "Latest approval placeholder" in markdown
    assert "LINE31 Post-Expert Answer Sequence" in markdown
    assert "run_line31_post_expert_answer_sequence.py --json" in markdown
    assert "Send the Oracle pack to the external expert." in markdown
    assert "`Send the Oracle pack to the external expert.`" not in markdown
    assert "/tmp/post_expert_summary.md" in markdown
    assert "Latest drop-intake checklist" in markdown
    assert "Validate the latest intake folder from the stable current pointer first" in markdown
    assert "validate_line31_current_final_creative_drop.py --json" in markdown
    assert "Latest Drop-Intake Commands" in markdown
    assert "Final creative mapping" in markdown
    assert "Owner approval phrase source" in markdown
    assert "Preferred One-Shot Command" in markdown


def test_current_status_command_outputs_json(tmp_path: Path) -> None:
    json_path = tmp_path / "status.json"
    md_path = tmp_path / "status.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/write_line31_current_launch_status.py",
            "--json-path",
            str(json_path),
            "--markdown-path",
            str(md_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ready_to_publish"] is False
    if (
        payload["latest_meta_current_readonly_snapshot"]["current_state_summary"].get(
            "ads_by_adset_count"
        )
        == 3
        and str(
            payload["latest_meta_current_readonly_snapshot"][
                "current_state_summary"
            ].get("adset_daily_budget")
        )
        == "3093"
        and payload["latest_line31_live_customer_label_probe"].get("gate")
        == "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
    ):
        assert payload["status"] == (
            "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
        )
        assert payload["owner_facing_publish_status"] == (
            "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION"
        )
        assert not any(
            "still shows customer-visible ACMEWEAR LINE31 copy" in item
            for item in payload["missing_or_pending"]
        )
        assert not any(
            "three LINE31 Meta ads are not live/source-verified" in item
            for item in payload["missing_or_pending"]
        )
    assert "mapping_path" in payload
    assert "approval_phrase_path" in payload
    assert payload["latest_web_deploy_approval_packet"][
        "customer_visible_copy_contract"
    ]["required_customer_visible_label"] == "AcmeWear 3в1"
    assert payload["latest_web_deploy_approval_packet"]["live_probe_before_deploy"][
        "contains_forbidden_customer_copy"
    ] is True
    assert payload["latest_web_deploy_approval_packet"]["live_probe_before_deploy"][
        "contains_required_customer_copy"
    ] is False
    assert "latest_line31_live_customer_label_probe" in payload
    assert "latest_expert_launch_answer_intake" in payload
    assert payload["latest_expert_launch_answer_intake"]["intake_command"] == (
        "python3 scripts/ingest_line31_expert_launch_answer.py --json"
    )
    assert "latest_post_expert_answer_sequence" in payload
    assert payload["latest_post_expert_answer_sequence"]["sequence_command"] == (
        "python3 scripts/run_line31_post_expert_answer_sequence.py --json"
    )
    if payload["latest_expert_launch_answer_intake"]["exists"]:
        assert payload["latest_expert_launch_answer_intake"]["gate"] in {
            "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE",
            "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE",
            "YELLOW_LINE31_EXPERT_START_AS_IS_PREFLIGHT_REFRESH_REQUIRED_NO_WRITE",
            "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE",
            "YELLOW_LINE31_EXPERT_HOLD_PAUSED_NO_WRITE",
            "YELLOW_LINE31_EXPERT_DECISION_UNCLASSIFIED_NO_WRITE",
            "RED_LINE31_EXPERT_ANSWER_AMBIGUOUS_NO_WRITE",
            "RED_LINE31_EXPERT_ANSWER_INTAKE_INPUT_MISSING_NO_WRITE",
        }
        assert "action" in payload["latest_expert_launch_answer_intake"][
            "next_safe_action"
        ]
    assert isinstance(
        payload["latest_meta_line31_publish_preflight"][
            "required_meta_write_phrase_present"
        ],
        bool,
    )
    assert payload["latest_meta_line31_publish_preflight"]["meta_write_attempted"] is False
    assert payload["latest_meta_live_write_ready_stopline"]["gate"] == (
        "GREEN_READY_FOR_EXACT_META_API_LIVE_WRITE_APPROVAL_NO_WRITE"
    )
    assert payload["latest_meta_live_write_ready_stopline"][
        "approval_paste_file"
    ].endswith("OWNER_PASTED_EXACT_META_API_LIVE_WRITE_APPROVAL.txt")
    assert payload["latest_meta_live_write_ready_stopline"][
        "required_live_write_phrase_file"
    ].endswith("REQUIRED_EXACT_META_API_LIVE_WRITE_APPROVAL_PHRASE.txt")
    assert payload["latest_meta_live_write_ready_stopline"]["meta_write_attempted"] is False
    assert payload["latest_meta_api_live_partial_blocker"]["gate"] == (
        "YELLOW_PARTIAL_META_LAUNCH_BLOCKED_BY_META_APP_DEV_MODE"
    )
    assert payload["latest_meta_api_live_partial_blocker"][
        "last_source_backed_exact_ad_count"
    ] == 0
    assert payload["latest_meta_api_live_partial_blocker"][
        "three_ads_live_verified"
    ] is False
    assert (
        payload["latest_meta_api_live_partial_blocker"]["latest_blocker"][
            "error_subcode"
        ]
        == 1885183
    )
    assert "development mode" in payload["latest_meta_api_live_partial_blocker"][
        "latest_blocker"
    ]["message"]
    assert payload["latest_meta_budget_currency_stopline"]["gate"] == (
        "RED_META_BUDGET_CURRENCY_MISMATCH_STOPLINE"
    )
    assert payload["latest_meta_budget_currency_stopline"]["owner_observation"][
        "observed_budget_display"
    ] == "$150.00"
    assert payload["latest_meta_budget_currency_stopline"]["approved_intent"][
        "daily_budget_kzt"
    ] == 15000
    assert payload["latest_meta_budget_currency_stopline"]["safety_pause"]["gate"] == (
        "GREEN_LINE31_META_PARTIAL_SHELL_SAFETY_PAUSED"
    )
    assert payload["latest_meta_budget_currency_stopline"]["currency_safe_preflight"][
        "daily_budget_minor_units"
    ] == 3093
    assert payload["latest_meta_budget_currency_stopline"]["currency_safe_preflight"][
        "daily_budget_account_currency"
    ] == "30.93"
    assert payload["latest_meta_budget_currency_stopline"]["currency_safe_preflight"][
        "existing_paused_adset_daily_budget"
    ] == "15000"
    assert (
        payload["latest_meta_budget_currency_stopline"]["meta_objects"]["adset_id"]
        == "120245481997290641"
    )
    assert payload["latest_meta_budget_currency_stopline"]["handoff"]["path"].endswith(
        "NEXT_OWNER_DECISION_AND_EXECUTION_HANDOFF.md"
    )
    assert payload["latest_meta_partial_shell_safety_pause"]["gate"] == (
        "GREEN_LINE31_META_PARTIAL_SHELL_SAFETY_PAUSED"
    )
    assert payload["latest_meta_partial_shell_safety_pause"]["verification"][
        "campaign_status_paused"
    ] is True
    assert payload["latest_meta_partial_shell_safety_pause"]["verification"][
        "adset_status_paused"
    ] is True
    assert payload["latest_meta_partial_shell_safety_pause"]["after"]["campaign"][
        "status"
    ] == "PAUSED"
    assert payload["latest_meta_partial_shell_safety_pause"]["after"]["adset"][
        "status"
    ] == "PAUSED"
    assert payload["latest_deploy_liveqa_sequence"][
        "meta_publish_approval_phrase_present"
    ] is True
    assert Path(payload["json_path"]).is_file()
    assert Path(payload["markdown_path"]).is_file()
