#!/usr/bin/env python3
"""Validate the latest LINE31 final creative drop folder from the stable status pointer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_drop_intake import (  # noqa: E402
    DEFAULT_FINAL_ASSET_URI,
    DEFAULT_KASPI_CTA_URL,
    DEFAULT_LANDING_URL,
    DEFAULT_TEMPLATE,
    _duration_seconds,
    validate_drop,
)
from scripts.prepare_line31_launch_readiness_from_assets import (  # noqa: E402
    DEFAULT_APPROVAL_PHRASE_PATH,
)

DEFAULT_STATUS_PATH = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.json"


def _load_json(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"current status JSON does not exist: {resolved}")
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"current status JSON is invalid: {resolved}: {exc}") from exc


def _latest_drop(status: dict[str, Any]) -> dict[str, Any]:
    latest = status.get("latest_drop_intake")
    if not isinstance(latest, dict):
        raise ValueError("current status JSON is missing latest_drop_intake")
    if not latest.get("asset_dir"):
        raise ValueError("current status JSON is missing latest_drop_intake.asset_dir")
    return latest


def validate_current_drop(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status_path.expanduser().resolve()
    status = _load_json(status_path)
    latest = _latest_drop(status)
    asset_dir = Path(str(latest["asset_dir"]))
    approval_phrase_path = args.approval_phrase_path
    if approval_phrase_path == DEFAULT_APPROVAL_PHRASE_PATH:
        current_phrase = str(status.get("approval_phrase_path") or "").strip()
        if current_phrase:
            approval_phrase_path = Path(current_phrase)
    approval_text_file = args.approval_text_file
    if args.use_current_approval_file or (args.require_approval and not approval_text_file):
        current_approval = latest.get("approval_text_file")
        if current_approval:
            approval_text_file = Path(str(current_approval))

    validator_payload = validate_drop(
        argparse.Namespace(
            template=args.template,
            asset_dir=asset_dir,
            video=args.video,
            thumbnail=args.thumbnail,
            creative_id=args.creative_id,
            final_asset_uri=args.final_asset_uri,
            landing_url=args.landing_url,
            kaspi_marketplace_cta_url=args.kaspi_marketplace_cta_url,
            duration_seconds=args.duration_seconds,
            utm_placement=args.utm_placement,
            utm_content=args.utm_content,
            aspect_ratio=args.aspect_ratio,
            language=args.language,
            primary_cta=args.primary_cta,
            owner_notes=args.owner_notes,
            approval_text_file=approval_text_file,
            approval_phrase_path=approval_phrase_path,
            tracking_qa_evidence_file=args.tracking_qa_evidence_file,
            require_approval=args.require_approval,
        )
    )
    return {
        "ok": bool(validator_payload["ok"]),
        "gate": validator_payload["gate"],
        "current_status_path": str(status_path),
        "current_status_generated_at": status.get("generated_at", ""),
        "latest_drop_intake": {
            "dir": latest.get("dir", ""),
            "asset_dir": latest.get("asset_dir", ""),
            "approval_text_file": latest.get("approval_text_file", ""),
            "checklist_path": latest.get("checklist_path", ""),
            "manifest": latest.get("manifest", ""),
        },
        "effective_approval_text_file": str(approval_text_file or ""),
        "effective_approval_phrase_path": str(approval_phrase_path or ""),
        "validator": validator_payload,
        "no_external_writes_performed": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--thumbnail", type=Path, default=None)
    parser.add_argument("--creative-id", default="line31_countrywide_v1")
    parser.add_argument("--final-asset-uri", default=DEFAULT_FINAL_ASSET_URI)
    parser.add_argument("--landing-url", default=DEFAULT_LANDING_URL)
    parser.add_argument("--kaspi-marketplace-cta-url", default=DEFAULT_KASPI_CTA_URL)
    parser.add_argument("--duration-seconds", type=_duration_seconds, default=18)
    parser.add_argument("--utm-placement", default="reels")
    parser.add_argument("--utm-content", default=None)
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--primary-cta", default="Shop now")
    parser.add_argument("--owner-notes", default="")
    parser.add_argument("--approval-text-file", type=Path, default=None)
    parser.add_argument(
        "--use-current-approval-file",
        action="store_true",
        help="Validate against latest_drop_intake.approval_text_file from the current status pointer.",
    )
    parser.add_argument("--approval-phrase-path", type=Path, default=DEFAULT_APPROVAL_PHRASE_PATH)
    parser.add_argument(
        "--tracking-qa-evidence-file",
        type=Path,
        default=None,
        help="Current LINE31 tracking/redirect QA JSON evidence; required when approval readiness is required.",
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Also require exact owner approval evidence from --approval-text-file or the current approval placeholder.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = validate_current_drop(args)
    except ValueError as exc:
        payload = {
            "ok": False,
            "gate": "NOT_READY",
            "errors": [str(exc)],
            "no_external_writes_performed": True,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {payload['gate']}")
        print(f"Assets: {payload['latest_drop_intake']['asset_dir']}")
        for error in payload["validator"]["errors"]:
            print(f"ERROR: {error}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
