#!/usr/bin/env python3
"""Validate a LINE31 final creative drop folder before running launch helpers."""

from __future__ import annotations

import argparse
from argparse import Namespace
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_line31_final_creative_mapping import build_mapping  # noqa: E402
from scripts.prepare_line31_launch_readiness_from_assets import (  # noqa: E402
    DEFAULT_APPROVAL_PHRASE_PATH,
    _resolve_asset_inputs,
)
from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_TEMPLATE,
    validate_mapping,
)
DEFAULT_FINAL_ASSET_URI = "https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4"
DEFAULT_LANDING_URL = "https://acmewear.pro/line31"
DEFAULT_KASPI_CTA_URL = "https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/"


def _validate_mapping_without_writing(mapping: dict[str, Any]) -> list[str]:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".json",
        delete=False,
    ) as handle:
        json.dump(mapping, handle, ensure_ascii=False)
        temp_path = Path(handle.name)
    try:
        result = validate_mapping(temp_path, template_ok=False)
    finally:
        temp_path.unlink(missing_ok=True)

    allowed_errors = {
        "publish_authority.approved must be true for publish readiness",
    }
    publish = mapping.get("publish_authority") or {}
    if not publish.get("approved"):
        allowed_errors.update(
            {
                "tracking_redirect_qa.gate is required",
                "tracking_redirect_qa.evidence_path is required",
                "tracking_redirect_qa.evidence_sha256 is required",
            }
        )
    return [error for error in result.errors if error not in allowed_errors]


def validate_drop(args: argparse.Namespace) -> dict[str, Any]:
    errors: list[str] = []
    video: Path | None = None
    thumbnail: Path | None = None
    try:
        video, thumbnail = _resolve_asset_inputs(
            Namespace(asset_dir=args.asset_dir, video=args.video, thumbnail=args.thumbnail)
        )
    except ValueError as exc:
        errors.append(str(exc))

    approval_ready = False
    approval_error = ""
    if args.approval_text_file:
        try:
            build_mapping(
                Namespace(
                    template=args.template,
                    creative_id=args.creative_id,
                    asset_dir=args.asset_dir,
                    video=video,
                    thumbnail=thumbnail,
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
                    approval_phrase_path=str(args.approval_phrase_path),
                    creative_ready_declared=True,
                    owner_approved=True,
                    approval_evidence_file=args.approval_text_file,
                    tracking_qa_evidence_file=args.tracking_qa_evidence_file,
                )
            )
            approval_ready = True
        except ValueError as exc:
            approval_error = str(exc)
            errors.append(approval_error)
    elif args.require_approval:
        approval_error = "--approval-text-file is required when --require-approval is set"
        errors.append(approval_error)

    mapping_errors: list[str] = []
    if video and thumbnail:
        try:
            mapping = build_mapping(
                Namespace(
                    template=args.template,
                    creative_id=args.creative_id,
                    asset_dir=args.asset_dir,
                    video=video,
                    thumbnail=thumbnail,
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
                    approval_phrase_path=str(args.approval_phrase_path),
                    creative_ready_declared=True,
                    owner_approved=False,
                    approval_evidence_file=None,
                    tracking_qa_evidence_file=args.tracking_qa_evidence_file,
                )
            )
            mapping_errors = _validate_mapping_without_writing(mapping)
            errors.extend(mapping_errors)
        except ValueError as exc:
            mapping_errors = [str(exc)]
            errors.extend(mapping_errors)

    assets_ready = bool(video and thumbnail and not mapping_errors)
    ok = not errors
    gate = (
        "READY_FOR_ONE_SHOT_WITH_APPROVAL"
        if ok and approval_ready
        else "ASSETS_AND_URLS_READY_PENDING_APPROVAL"
        if ok
        else "NOT_READY"
    )
    return {
        "ok": ok,
        "gate": gate,
        "errors": errors,
        "asset_dir": str(args.asset_dir.expanduser().resolve()) if args.asset_dir else "",
        "resolved_video": str(video or ""),
        "resolved_thumbnail": str(thumbnail or ""),
        "assets_ready": assets_ready,
        "approval_ready": approval_ready,
        "approval_error": approval_error,
        "require_approval": args.require_approval,
        "final_asset_uri": args.final_asset_uri,
        "landing_url": args.landing_url,
        "kaspi_marketplace_cta_url": args.kaspi_marketplace_cta_url,
        "no_external_writes_performed": True,
    }


def _duration_seconds(raw: str) -> float | int:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--duration-seconds must be numeric") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("--duration-seconds must be greater than 0")
    return int(value) if value.is_integer() else value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--asset-dir", type=Path, required=True)
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
    parser.add_argument("--approval-phrase-path", type=Path, default=DEFAULT_APPROVAL_PHRASE_PATH)
    parser.add_argument(
        "--tracking-qa-evidence-file",
        type=Path,
        default=None,
        help="Current LINE31 tracking/redirect QA JSON evidence; required with approval readiness.",
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Also require the approval text file to contain the exact owner approval phrase.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = validate_drop(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {payload['gate']}")
        for error in payload["errors"]:
            print(f"ERROR: {error}")
        print(f"Video: {payload['resolved_video'] or '<missing>'}")
        print(f"Thumbnail: {payload['resolved_thumbnail'] or '<missing>'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
