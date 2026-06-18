from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.record_line31_owner_publish_approval import record_approval
from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase


APPROVAL_TEMPLATE = Path(
    "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
    "final_creative_publish_intake_and_approval.md"
)


def _phrase() -> str:
    return required_owner_approval_phrase(APPROVAL_TEMPLATE)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_media(tmp_path: Path) -> tuple[Path, Path]:
    video = tmp_path / "final.mp4"
    thumbnail = tmp_path / "thumb.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    return video, thumbnail


def _write_tracking_qa_evidence(tmp_path: Path) -> Path:
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


def _write_ready_pending_approval_mapping(tmp_path: Path) -> Path:
    video, thumbnail = _write_media(tmp_path)
    tracking = _write_tracking_qa_evidence(tmp_path)
    mapping = tmp_path / "mapping_ready_pending_approval.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_final_creative_mapping.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--video",
            str(video),
            "--thumbnail",
            str(thumbnail),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--creative-ready-declared",
            "--tracking-qa-evidence-file",
            str(tracking),
            "--output",
            str(mapping),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return mapping


def test_record_approval_from_file_writes_evidence_and_hash(tmp_path: Path) -> None:
    source = tmp_path / "approval.txt"
    source.write_text(f"Owner says:\n\n{_phrase()}\n", encoding="utf-8")
    output_dir = tmp_path / "evidence"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-text-file",
            str(source),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    evidence = Path(payload["approval_evidence_path"])
    assert evidence.exists()
    assert payload["approval_evidence_sha256"] == _sha(evidence)
    assert _phrase() in evidence.read_text(encoding="utf-8")
    assert payload["next_mapping_flags"] == [
        "--owner-approved",
        "--approval-evidence-file",
        str(evidence),
    ]
    assert payload["mapping_ready_for_approval_required"] is False
    assert payload["mapping_ready_for_approval"] is False


def test_record_approval_requires_mapping_ready_when_requested(tmp_path: Path) -> None:
    source = tmp_path / "approval.txt"
    source.write_text(f"Owner says:\n\n{_phrase()}\n", encoding="utf-8")
    mapping = _write_ready_pending_approval_mapping(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-text-file",
            str(source),
            "--mapping",
            str(mapping),
            "--require-mapping-ready",
            "--output-dir",
            str(tmp_path / "evidence"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mapping_ready_for_approval_required"] is True
    assert payload["mapping_ready_for_approval"] is True
    evidence = Path(payload["approval_evidence_path"])
    assert "`--require-mapping-ready` passed" in evidence.read_text(encoding="utf-8")


def test_record_approval_accepts_plain_generated_phrase_file(tmp_path: Path) -> None:
    phrase_file = tmp_path / "NEXT_META_PUBLISH_APPROVAL_PHRASE.txt"
    phrase = "I approve LINE31_COUNTRYWIDE_META_PUBLISH for exact generated current phrase."
    phrase_file.write_text(phrase + "\n", encoding="utf-8")
    source = tmp_path / "approval.txt"
    source.write_text(phrase + "\n", encoding="utf-8")
    mapping = _write_ready_pending_approval_mapping(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-phrase-path",
            str(phrase_file),
            "--approval-text-file",
            str(source),
            "--mapping",
            str(mapping),
            "--require-mapping-ready",
            "--output-dir",
            str(tmp_path / "evidence"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    evidence = Path(payload["approval_evidence_path"])
    assert phrase in evidence.read_text(encoding="utf-8")
    assert payload["approval_phrase_path"].endswith("NEXT_META_PUBLISH_APPROVAL_PHRASE.txt")


def test_record_approval_rejects_unready_mapping_when_required(tmp_path: Path) -> None:
    source = tmp_path / "approval.txt"
    source.write_text(f"Owner says:\n\n{_phrase()}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-text-file",
            str(source),
            "--mapping",
            str(
                Path(
                    "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
                    "final_creative_asset_mapping_template.json"
                )
            ),
            "--require-mapping-ready",
            "--output-dir",
            str(tmp_path / "evidence"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "mapping is not ready for owner approval" in completed.stderr
    assert "tracking_redirect_qa.evidence_path is required" in completed.stderr
    assert not list((tmp_path / "evidence").glob("line31_owner_publish_approval_*.md"))


def test_record_approval_from_stdin(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--from-stdin",
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
        input=f"{_phrase()}\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert Path(payload["approval_evidence_path"]).exists()


def test_record_approval_rejects_non_exact_text(tmp_path: Path) -> None:
    source = tmp_path / "approval.txt"
    source.write_text("I approve LINE31 in spirit.\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-text-file",
            str(source),
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "does not contain the exact required LINE31 owner approval phrase" in completed.stderr
    assert not list(tmp_path.glob("line31_owner_publish_approval_*.md"))


def test_record_approval_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "approval.txt"
    source.write_text(_phrase(), encoding="utf-8")
    output = tmp_path / "approval_evidence.md"
    output.write_text("already here", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_line31_owner_publish_approval.py",
            "--approval-text-file",
            str(source),
            "--output",
            str(output),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "pass --overwrite" in completed.stderr


def test_record_approval_function_requires_one_input(tmp_path: Path) -> None:
    class Args:
        approval_text_file = None
        from_stdin = False
        approval_phrase_path = APPROVAL_TEMPLATE
        mapping = Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_asset_mapping_template.json"
        )
        output_dir = tmp_path
        output = None
        overwrite = False
        require_mapping_ready = False

    try:
        record_approval(Args())
    except ValueError as exc:
        assert "approval input required" in str(exc)
    else:
        raise AssertionError("missing approval input should fail")
