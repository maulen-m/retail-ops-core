from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _qa_payload(*, raw_kaspi_href: bool = False) -> dict:
    redirect_slugs = [
        "starry-black",
        "ivory-white-starry-black",
        "misty-blue",
        "cardamom-green-olive-green",
        "whale-blue",
        "iris-purple",
        "ivory",
        "espresso",
    ]
    return {
        "gate": "GREEN",
        "qa_scope": "live_postdeploy",
        "target_base_url": "https://acmewear.pro",
        "landing": {
            "path": "/line31",
            "status": 200,
            "tracked_params_in_runtime_config": [
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_placement",
            ],
            "missing_expected_utm_params": [],
            "primary_cta_route": "/go/starry-black",
            "chooser_fallback_cta_route": "/go/ivory-white-starry-black",
            "raw_kaspi_href_in_landing_html": raw_kaspi_href,
        },
        "browser_events": [
            {"event_name": name, "api_status": 204, "stored": True}
            for name in [
                "PageView",
                "ViewContent",
                "ColorSelect",
                "QualifiedVisit",
                "KaspiClick",
                "HighIntentKaspiClick",
            ]
        ],
        "redirect_routes": [
            {
                "slug": slug,
                "http_status": 302,
                "destination_route_matches_registry": True,
                "tracked_utm_keys_missing_or_wrong": [],
                "landing_color_preserved": True,
                "landing_source_preserved": True,
            }
            for slug in redirect_slugs
        ],
        "fail_closed_checks": {
            "unknown_color_status": 404,
            "browser_spoofed_kaspi_redirect_status": 400,
            "fake_purchase_status": 400,
        },
        "no_fake_ecommerce_events": {
            "fake_purchase_rejected": True,
            "forbidden_events_checked": [
                "Purchase",
                "AddToCart",
                "InitiateCheckout",
                "AddPaymentInfo",
            ],
        },
    }


def _fixture_status(
    tmp_path: Path,
    *,
    raw_kaspi_href: bool = False,
    current_meta_retained_ui_gap: bool = False,
    preflight_green_owner_phrase_gated: bool = False,
) -> Path:
    qa = _write_json(tmp_path / "qa.json", _qa_payload(raw_kaspi_href=raw_kaspi_href))
    assets = []
    for index, creative_id in enumerate(
        ["line31_cw_a", "line31_cw_b", "line31_cw_c"],
        start=1,
    ):
        assets.append(
            {
                "creative_id": creative_id,
                "local_file_path": str(tmp_path / f"video_{index}.mp4"),
                "final_asset_uri": f"https://cdn.acmewear.kz/line31/video_{index}.mp4",
                "thumbnail_path_or_uri": str(tmp_path / f"thumb_{index}.png"),
                "video_sha256": "a" * 64,
                "thumbnail_sha256": "b" * 64,
                "landing_url": (
                    "https://acmewear.pro/line31?utm_source=meta&utm_medium=paid_social"
                    f"&utm_campaign=line31_countrywide&utm_content={creative_id}&utm_placement=reels"
                ),
                "utm_content": creative_id,
                "utm_placement": "reels",
                "kaspi_marketplace_cta_url": "https://acmewear.pro/go/starry-black",
            }
        )
    mapping = _write_json(
        tmp_path / "mapping.json",
        {
            "tracking_redirect_qa": {
                "required": True,
                "gate": "GREEN",
                "evidence_path": str(qa),
                "evidence_sha256": "c" * 64,
            },
            "assets": assets,
        },
    )
    final_manifest = _write_json(
        tmp_path / "asset_manifest.json",
        {
            "campaign_shape": {
                "ad_count": 3,
                "daily_budget_kzt": 15000,
                "hard_cap_kzt": 20000,
                "landing_url": "https://acmewear.pro/line31",
            },
            "landing_cta_priority": [
                "starry_black",
                "wib_mixed_color_set",
                "blue_misty",
                "olive_green",
                "remaining_colors",
                "espresso_last",
            ],
        },
    )
    preflight_payload = {
        "launch_shape": {
            "ad_count": 3,
            "daily_budget_kzt": 15000,
            "hard_cap_kzt": 20000,
            "landing_url": "https://acmewear.pro/line31",
            "publish_status": "ACTIVE",
        },
    }
    if preflight_green_owner_phrase_gated:
        preflight_payload.update(
            {
                "gate": "GREEN_META_LINE31_PUBLISH_PREFLIGHT_READY_NO_WRITE",
                "errors": [],
                "write_gate": {
                    "ok": False,
                    "reasons": ["owner approval text is empty"],
                },
            }
        )
    else:
        preflight_payload["errors"] = [
            "publish_authority.approved must be true",
            "publish_authority.approval_evidence_path is required",
        ]
    preflight = _write_json(tmp_path / "meta_preflight.json", preflight_payload)
    current_meta = _write_json(
        tmp_path / "meta_current_snapshot.json",
        {
            "gate": "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_WITH_UI_ONLY_REVIEW_NO_WRITE"
            if current_meta_retained_ui_gap
            else "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_NO_WRITE",
            "checks_failed": 0,
            "checks_review": 1 if current_meta_retained_ui_gap else 0,
            "current_state_summary": {
                "campaign_status": "PAUSED",
                "adset_status": "PAUSED",
                "adset_daily_budget": "3093",
                "ads_by_adset_count": 3,
                "customer_visible_message": "Женский комплект AcmeWear 3в1. Закажи на Каспи и получи сумку в подарок!",
                "customer_visible_cta": "ORDER_NOW",
                "landing_url": "https://acmewear.pro/line31",
            },
            "retained_ui_only_gaps": [
                "multi_advertiser_ads_off_not_verified_by_graph_api"
            ]
            if current_meta_retained_ui_gap
            else [],
        },
    )
    live_label = _write_json(
        tmp_path / "live_customer_label_probe.json",
        {
            "gate": "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE",
            "checks_failed": 0,
            "summary": {
                "contains_required_customer_label": True,
                "contains_forbidden_customer_label": False,
                "contains_raw_kaspi_product_href": False,
            },
        },
    )
    bridge = _write_json(
        tmp_path / "bridge.json",
        {
            "gate": "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE",
            "external_write_attempted": False,
            "meta_write_attempted": False,
            "owner_paste_file": str(tmp_path / "owner_line31.txt"),
            "meta_api_live_write_approval_file": str(tmp_path / "owner_meta.txt"),
        },
    )
    monitoring = _write_json(
        tmp_path / "monitoring.json",
        {
            "gate": "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE",
            "external_write_attempted": False,
            "meta_write_attempted": False,
            "truth_separation_contract": [
                "Meta traffic truth: impressions, clicks, LPV, spend, and ad delivery only.",
                "Website truth: PageView, ViewContent, ColorSelect, QualifiedVisit, KaspiClick, and HighIntentKaspiClick.",
                "Redirect truth: /go/:color 302 destination, UTM preservation, landing_color, and landing_source.",
                "Kaspi order truth: real order rows only; no purchase is inferred from Meta or website clicks.",
                "Attribution truth: directional until order matching proves stronger evidence.",
            ],
        },
    )
    return _write_json(
        tmp_path / "status.json",
        {
            "mapping_path": str(mapping),
            "latest_final_creative_assets": {"manifest": str(final_manifest)},
            "latest_meta_line31_publish_preflight": {"manifest": str(preflight)},
            "latest_meta_current_readonly_snapshot": {"manifest": str(current_meta)},
            "latest_line31_live_customer_label_probe": {"manifest": str(live_label)},
            "latest_meta_publish_bridge": {"manifest": str(bridge)},
            "latest_post_publish_monitoring_packet": {"manifest": str(monitoring)},
        },
    )


def test_customer_journey_traceability_audit_green(tmp_path: Path) -> None:
    status = _fixture_status(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_customer_journey_traceability_audit.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "trace_green",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == (
        "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
    )
    assert payload["checks_failed"] == 0
    assert payload["external_write_attempted"] is False
    assert payload["meta_write_attempted"] is False
    assert "Meta ad CTA" in payload["journey_chain"][0]

    rows = list(csv.DictReader(Path(payload["checks_csv"]).open(encoding="utf-8")))
    assert {row["status"] for row in rows} == {"PASS"}
    assert any(row["check"] == "browser_event_HighIntentKaspiClick_stored" for row in rows)
    assert any(row["check"] == "redirect_starry-black_utm_preserved" for row in rows)
    closeout = Path(payload["output_dir"]) / "closeout.md"
    assert "Checks failed: `0`" in closeout.read_text(encoding="utf-8")


def test_customer_journey_traceability_audit_yellow_for_raw_kaspi_href(
    tmp_path: Path,
) -> None:
    status = _fixture_status(tmp_path, raw_kaspi_href=True)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_customer_journey_traceability_audit.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "trace_yellow",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_REVIEW_REQUIRED_NO_WRITE"
    assert payload["checks_failed"] == 1
    assert payload["failed_checks"][0]["check"] == "landing_has_no_raw_kaspi_href"


def test_customer_journey_traceability_accepts_green_preflight_owner_phrase_gate(
    tmp_path: Path,
) -> None:
    status = _fixture_status(tmp_path, preflight_green_owner_phrase_gated=True)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_customer_journey_traceability_audit.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "trace_green_owner_phrase_gate",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["checks_failed"] == 0
    rows = list(csv.DictReader(Path(payload["checks_csv"]).open(encoding="utf-8")))
    assert any(
        row["check"] == "meta_preflight_only_approval_blocked"
        and row["status"] == "PASS"
        for row in rows
    )


def test_customer_journey_traceability_yellow_for_meta_ui_only_gap(
    tmp_path: Path,
) -> None:
    status = _fixture_status(tmp_path, current_meta_retained_ui_gap=True)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_customer_journey_traceability_audit.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "trace_yellow_meta_ui_gap",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_REVIEW_REQUIRED_NO_WRITE"
    assert payload["checks_failed"] == 1
    assert payload["failed_checks"][0]["check"] == "meta_current_multi_advertiser_ui_evidence"
