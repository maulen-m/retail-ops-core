from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validate_line31_final_creative_mapping import (
    DEFAULT_TEMPLATE,
    required_owner_approval_phrase,
    validate_mapping,
)

SYNTHETIC_APPROVAL = Path("tests/fixtures/line31/SYNTHETIC_APPROVAL_PHRASE.txt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approval_evidence(tmp_path: Path) -> Path:
    phrase = required_owner_approval_phrase(SYNTHETIC_APPROVAL)
    evidence = tmp_path / "owner_approval_evidence.md"
    evidence.write_text(
        f"# Owner Approval Evidence\n\nRecorded: 2026-06-01T16:00:00+05:00\n\n{phrase}\n",
        encoding="utf-8",
    )
    return evidence


def _tracking_qa_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "tracking_redirect_qa.json"
    evidence.write_text(
        json.dumps(
            {
                "gate": "GREEN",
                "qa_scope": "live_postdeploy",
                "target_base_url": "https://acmewear.pro",
                "root": {
                    "status": 200,
                    "tracked_params_in_runtime_config": [
                        "utm_source",
                        "utm_medium",
                        "utm_campaign",
                        "utm_content",
                        "utm_placement",
                    ],
                    "missing_expected_utm_params": [],
                },
                "browser_events": [
                    {"event_name": "PageView", "api_status": 204, "stored": True},
                    {"event_name": "ViewContent", "api_status": 204, "stored": True},
                    {"event_name": "ColorSelect", "api_status": 204, "stored": True},
                    {"event_name": "KaspiClick", "api_status": 204, "stored": True},
                    {"event_name": "HighIntentKaspiClick", "api_status": 204, "stored": True},
                ],
                "redirect_routes": [
                    {
                        "http_status": 302,
                        "destination_route_matches_registry": True,
                        "tracked_utm_keys_missing_or_wrong": [],
                        "landing_color_preserved": True,
                        "landing_source_preserved": True,
                    }
                ],
                "fallback_route": {
                    "http_status": 302,
                    "tracked_utm_keys_missing_or_wrong": [],
                    "landing_color_preserved": True,
                    "landing_source_preserved": True,
                },
                "fail_closed_checks": {
                    "browser_spoofed_kaspi_redirect_status": 400,
                    "fake_purchase_status": 400,
                    "unknown_color_status": 404,
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
                "failure_summary": [],
            }
        ),
        encoding="utf-8",
    )
    return evidence


def _tracking_qa_landing_evidence(tmp_path: Path) -> Path:
    evidence = _tracking_qa_evidence(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["landing"] = payload.pop("root")
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return evidence


def _base_mapping(video_path: Path, thumbnail_path: Path, approval_evidence: Path) -> dict:
    tracking_evidence = _tracking_qa_evidence(video_path.parent)
    return {
        "generated_at": "2026-06-01T15:30:00+05:00",
        "purpose": "LINE31 countrywide Meta launch final creative mapping intake template",
        "status": "FINAL_CREATIVE_READY",
        "source_gate": "GREEN_DRY_RUN_EOD_SUCCESS_WITH_DECLARED_WARNINGS",
        "creative_ready_declaration_received": True,
        "internal_kaspi_line31_campaigns_policy": (
            "KEEP_ON_UNTIL_OWNER_CREATIVE_READY_DECLARATION_AND_SEPARATE_PAUSE_APPROVAL"
        ),
        "landing_tracking_contract": {
            "utm_source": "meta",
            "utm_medium": "paid_social",
            "utm_campaign": "line31_countrywide",
            "required_fields": [
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_placement",
            ],
        },
        "tracking_redirect_qa": {
            "required": True,
            "gate": "GREEN",
            "evidence_path": str(tracking_evidence),
            "evidence_sha256": _sha(tracking_evidence),
        },
        "assets": [
            {
                "creative_id": "line31_test_001",
                "local_file_path": str(video_path),
                "final_asset_uri": "https://cdn.acmewear.kz/line31/final.mp4",
                "thumbnail_path_or_uri": str(thumbnail_path),
                "video_sha256": _sha(video_path),
                "thumbnail_sha256": _sha(thumbnail_path),
                "aspect_ratio": "9:16",
                "duration_seconds": 18,
                "language": "ru",
                "primary_cta": "Shop now",
                "landing_url": (
                    "https://acmewear.pro/line31?"
                    "utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&"
                    "utm_content=line31_test_001&utm_placement=reels"
                ),
                "utm_content": "line31_test_001",
                "utm_placement": "reels",
                "kaspi_marketplace_cta_url": "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
                "owner_notes": "",
            }
        ],
        "publish_authority": {
            "owner_approval_required": True,
            "approval_phrase_path": str(SYNTHETIC_APPROVAL),
            "approved": True,
            "approval_evidence_path": str(approval_evidence),
            "approval_evidence_sha256": _sha(approval_evidence),
        },
        "blocked_actions_without_separate_approval": [
            "pause_internal_kaspi_line31_campaigns",
        ],
    }


def _base_mapping_with_tracking(
    video_path: Path,
    thumbnail_path: Path,
    approval_evidence: Path,
    tracking_evidence: Path,
) -> dict:
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["tracking_redirect_qa"]["evidence_path"] = str(tracking_evidence)
    mapping["tracking_redirect_qa"]["evidence_sha256"] = _sha(tracking_evidence)
    return mapping


def test_tracked_pending_template_is_schema_valid_only() -> None:
    result = validate_mapping(DEFAULT_TEMPLATE, template_ok=True)

    assert result.ok, result.errors
    assert result.metrics["template_ok"] is True


def test_tracked_pending_template_is_not_publish_ready() -> None:
    result = validate_mapping(DEFAULT_TEMPLATE, template_ok=False)

    assert not result.ok
    assert any("publish_authority.approved" in error for error in result.errors)
    assert any("tracking_redirect_qa.gate" in error for error in result.errors)
    assert result.metrics["assets_count"] >= 1


def test_publish_ready_mapping_validates_local_hashes_and_utm(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(_base_mapping(video_path, thumbnail_path, approval_evidence), ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_mapping(mapping_path)

    assert result.ok, result.errors
    assert result.metrics["local_video_hashes_checked"] == 1
    assert result.metrics["local_thumbnail_hashes_checked"] == 1
    assert result.metrics["approval_evidence_checked"] == 1
    assert result.metrics["tracking_redirect_qa_checked"] == 1


def test_required_owner_approval_phrase_accepts_plain_exact_phrase_file(tmp_path: Path) -> None:
    phrase_file = tmp_path / "NEXT_META_PUBLISH_APPROVAL_PHRASE.txt"
    phrase_file.write_text(
        "I approve LINE31_COUNTRYWIDE_META_PUBLISH for exact current mapping.\n",
        encoding="utf-8",
    )

    phrase = required_owner_approval_phrase(phrase_file)

    assert phrase == "I approve LINE31_COUNTRYWIDE_META_PUBLISH for exact current mapping."


def test_publish_ready_mapping_accepts_current_landing_tracking_qa_shape(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    tracking_evidence = _tracking_qa_landing_evidence(tmp_path)
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(
            _base_mapping_with_tracking(
                video_path,
                thumbnail_path,
                approval_evidence,
                tracking_evidence,
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = validate_mapping(mapping_path)

    assert result.ok, result.errors
    assert result.metrics["tracking_redirect_qa_checked"] == 1


def test_publish_ready_mapping_rejects_placeholder_urls(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["assets"][0]["final_asset_uri"] = "https://example-cdn/line31/final_video.mp4"
    mapping["assets"][0]["kaspi_marketplace_cta_url"] = "https://kaspi.kz/shop/..."
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("final_asset_uri must not be a placeholder/example URI" in error for error in result.errors)
    assert any(
        "kaspi_marketplace_cta_url must not be a placeholder/example URI" in error
        for error in result.errors
    )


def test_publish_ready_mapping_fails_on_hash_mismatch(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["assets"][0]["video_sha256"] = "0" * 64
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("video_sha256 mismatch" in error for error in result.errors)


def test_publish_ready_mapping_rejects_local_thumbnail_without_sha(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["assets"][0]["thumbnail_sha256"] = ""
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("thumbnail_sha256 is required for local thumbnail" in error for error in result.errors)


def test_publish_ready_mapping_fails_without_tracking_redirect_qa(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["tracking_redirect_qa"]["evidence_path"] = ""
    mapping["tracking_redirect_qa"]["evidence_sha256"] = ""
    mapping["tracking_redirect_qa"]["gate"] = ""
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("tracking_redirect_qa.evidence_path is required" in error for error in result.errors)


def test_publish_ready_mapping_fails_when_landing_url_drops_placement(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["assets"][0]["landing_url"] = (
        "https://acmewear.pro/line31?"
        "utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&"
        "utm_content=line31_test_001"
    )
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("utm_placement" in error for error in result.errors)


def test_publish_ready_mapping_fails_without_approval_evidence(tmp_path: Path) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = _approval_evidence(tmp_path)
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["publish_authority"]["approval_evidence_path"] = ""
    mapping["publish_authority"]["approval_evidence_sha256"] = ""
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("approval_evidence_path is required" in error for error in result.errors)


def test_publish_ready_mapping_fails_when_approval_phrase_is_not_exact(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "final.mp4"
    thumbnail_path = tmp_path / "thumb.png"
    video_path.write_bytes(b"fake-video")
    thumbnail_path.write_bytes(b"fake-thumbnail")
    approval_evidence = tmp_path / "bad_approval.md"
    approval_evidence.write_text("I approve something else.\n", encoding="utf-8")
    mapping = _base_mapping(video_path, thumbnail_path, approval_evidence)
    mapping["publish_authority"]["approval_evidence_sha256"] = _sha(approval_evidence)
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    result = validate_mapping(mapping_path)

    assert not result.ok
    assert any("does not contain exact required owner approval phrase" in error for error in result.errors)
