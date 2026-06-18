#!/usr/bin/env python3
"""Prepare a LINE31 final creative mapping from local video and thumbnail files."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_MAPPING,
    required_owner_approval_phrase,
    validate_mapping,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_APPROVAL_PATH = (
    "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
    "final_creative_publish_intake_and_approval.md"
)
VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".webm"}
THUMBNAIL_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _existing_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved


def _existing_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"{label} is not a directory: {resolved}")
    return resolved


def _detect_one_asset(asset_dir: Path, *, extensions: set[str], label: str) -> Path:
    candidates = sorted(
        path
        for path in asset_dir.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )
    if len(candidates) != 1:
        allowed = ", ".join(sorted(extensions))
        rendered = ", ".join(path.name for path in candidates) or "none"
        raise ValueError(
            f"--asset-dir expected exactly one {label} file ({allowed}); "
            f"found {len(candidates)}: {rendered}"
        )
    return candidates[0].resolve()


def _resolve_asset_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    raw_asset_dir = getattr(args, "asset_dir", None)
    asset_dir = _existing_dir(raw_asset_dir, "asset directory") if raw_asset_dir else None
    raw_video = getattr(args, "video", None)
    raw_thumbnail = getattr(args, "thumbnail", None)

    if raw_video:
        video = _existing_file(raw_video, "video")
    elif asset_dir:
        video = _detect_one_asset(asset_dir, extensions=VIDEO_EXTENSIONS, label="video")
    else:
        raise ValueError("--video is required unless --asset-dir contains exactly one video file")

    if raw_thumbnail:
        thumbnail = _existing_file(raw_thumbnail, "thumbnail")
    elif asset_dir:
        thumbnail = _detect_one_asset(
            asset_dir,
            extensions=THUMBNAIL_EXTENSIONS,
            label="thumbnail",
        )
    else:
        raise ValueError(
            "--thumbnail is required unless --asset-dir contains exactly one thumbnail file"
        )
    return video, thumbnail


def _duration_seconds(raw: str) -> float | int:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--duration-seconds must be numeric") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("--duration-seconds must be greater than 0")
    return int(value) if value.is_integer() else value


def _normalize_landing_url(
    landing_url: str,
    *,
    utm_content: str,
    utm_placement: str,
) -> str:
    parsed = urlparse(landing_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("utm_source", "meta")
    query.setdefault("utm_medium", "paid_social")
    query.setdefault("utm_campaign", "line31_countrywide")
    query["utm_content"] = utm_content
    query["utm_placement"] = utm_placement
    return urlunparse(parsed._replace(query=urlencode(query)))


def _load_template(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"template root must be an object: {path}")
    return data


def _status(*, creative_ready: bool, owner_approved: bool) -> str:
    if creative_ready and owner_approved:
        return "FINAL_CREATIVE_READY_OWNER_APPROVED"
    if creative_ready:
        return "FINAL_CREATIVE_READY_PENDING_OWNER_APPROVAL"
    return "FINAL_CREATIVE_MAPPING_DRAFT_PENDING_CREATIVE_READY_DECLARATION"


def build_mapping(args: argparse.Namespace) -> dict[str, Any]:
    template = _load_template(args.template)
    video, thumbnail = _resolve_asset_inputs(args)
    approval_evidence_path = None
    approval_evidence_sha = ""
    if args.owner_approved:
        approval_evidence_path = _existing_file(
            args.approval_evidence_file,
            "approval evidence file",
        )
        required_phrase = required_owner_approval_phrase(Path(args.approval_phrase_path))
        evidence_text = approval_evidence_path.read_text(encoding="utf-8")
        if required_phrase not in evidence_text:
            raise ValueError(
            "approval evidence file does not contain the exact required owner approval phrase"
            )
        approval_evidence_sha = _sha256(approval_evidence_path)
    tracking_qa_evidence_path = None
    tracking_qa_evidence_sha = ""
    raw_tracking_qa = getattr(args, "tracking_qa_evidence_file", None)
    if raw_tracking_qa:
        tracking_qa_evidence_path = _existing_file(
            raw_tracking_qa,
            "tracking/redirect QA evidence file",
        )
        tracking_qa_evidence_sha = _sha256(tracking_qa_evidence_path)
    utm_content = args.utm_content or args.creative_id
    landing_url = _normalize_landing_url(
        args.landing_url,
        utm_content=utm_content,
        utm_placement=args.utm_placement,
    )

    mapping = {
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "purpose": template.get(
            "purpose",
            "LINE31 countrywide Meta launch final creative mapping intake template",
        ),
        "status": _status(
            creative_ready=args.creative_ready_declared,
            owner_approved=args.owner_approved,
        ),
        "source_gate": template.get(
            "source_gate",
            "GREEN_DRY_RUN_EOD_SUCCESS_WITH_DECLARED_WARNINGS",
        ),
        "creative_ready_declaration_received": args.creative_ready_declared,
        "internal_kaspi_line31_campaigns_policy": template.get(
            "internal_kaspi_line31_campaigns_policy",
            "KEEP_ON_UNTIL_OWNER_CREATIVE_READY_DECLARATION_AND_SEPARATE_PAUSE_APPROVAL",
        ),
        "landing_tracking_contract": template.get(
            "landing_tracking_contract",
            {
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
        ),
        "tracking_redirect_qa": {
            "required": True,
            "gate": "GREEN" if tracking_qa_evidence_path else "",
            "evidence_path": str(tracking_qa_evidence_path or ""),
            "evidence_sha256": tracking_qa_evidence_sha,
            "refresh_policy": (
                "Refresh after final landing URL, UTM, /go/:color route, or website deploy changes; "
                "strict publish readiness cannot pass without this current local evidence hash."
            ),
        },
        "assets": [
            {
                "creative_id": args.creative_id,
                "local_file_path": str(video),
                "final_asset_uri": args.final_asset_uri,
                "thumbnail_path_or_uri": str(thumbnail),
                "video_sha256": _sha256(video),
                "thumbnail_sha256": _sha256(thumbnail),
                "aspect_ratio": args.aspect_ratio,
                "duration_seconds": args.duration_seconds,
                "language": args.language,
                "primary_cta": args.primary_cta,
                "landing_url": landing_url,
                "utm_content": utm_content,
                "utm_placement": args.utm_placement,
                "kaspi_marketplace_cta_url": args.kaspi_marketplace_cta_url,
                "owner_notes": args.owner_notes,
            }
        ],
        "publish_authority": {
            "owner_approval_required": True,
            "approval_phrase_path": args.approval_phrase_path,
            "approved": args.owner_approved,
            "approval_evidence_path": str(approval_evidence_path or ""),
            "approval_evidence_sha256": approval_evidence_sha,
        },
        "blocked_actions_without_separate_approval": template.get(
            "blocked_actions_without_separate_approval",
            [
                "pause_internal_kaspi_line31_campaigns",
                "unrelated_campaign_changes",
                "price_changes",
                "stock_changes",
                "kaspi_webui_api_writes",
                "production_db_writes_beyond_required_launch_logging",
                "workbook_writes",
                "scheduler_changes",
                "supplier_payment",
                "po_commitment",
                "cash_movement",
                "owner_publication_outside_this_launch",
            ],
        ),
    }
    return mapping


def _write_json(path: Path, data: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"output exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _validate_prepared_mapping(mapping: dict[str, Any]) -> list[str]:
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

    allowed_errors: set[str] = set()
    if not mapping.get("creative_ready_declaration_received"):
        allowed_errors.add(
            "creative_ready_declaration_received must be true for publish readiness"
        )
    publish = mapping.get("publish_authority") or {}
    if not publish.get("approved"):
        allowed_errors.add("publish_authority.approved must be true for publish readiness")
        allowed_errors.update(
            {
                "tracking_redirect_qa.gate is required",
                "tracking_redirect_qa.evidence_path is required",
                "tracking_redirect_qa.evidence_sha256 is required",
            }
        )

    return [error for error in result.errors if error not in allowed_errors]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Example: python3 scripts/prepare_line31_final_creative_mapping.py "
            "--creative-id line31_countrywide_v1 --asset-dir /path/final_assets "
            "--final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 "
            "--duration-seconds 18 --utm-placement reels "
            "--landing-url 'https://acmewear.pro/line31' "
            "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
            "--creative-ready-declared --output exports/validation/.../"
            "final_creative_asset_mapping_template.json --overwrite"
        ),
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--creative-id", required=True)
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=None,
        help=(
            "Optional final creative drop folder. If --video or --thumbnail is omitted, "
            "the folder must contain exactly one matching video or thumbnail file."
        ),
    )
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--thumbnail", type=Path, default=None)
    parser.add_argument("--final-asset-uri", required=True)
    parser.add_argument("--landing-url", required=True)
    parser.add_argument(
        "--kaspi-marketplace-cta-url",
        required=True,
        help="Final marketplace CTA URL used from the landing page.",
    )
    parser.add_argument("--duration-seconds", type=_duration_seconds, required=True)
    parser.add_argument("--utm-placement", required=True)
    parser.add_argument(
        "--utm-content",
        default=None,
        help="Defaults to --creative-id.",
    )
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--primary-cta", default="Shop now")
    parser.add_argument("--owner-notes", default="")
    parser.add_argument("--approval-phrase-path", default=DEFAULT_APPROVAL_PATH)
    parser.add_argument(
        "--creative-ready-declared",
        action="store_true",
        help="Set only after owner declares the final creative files ready.",
    )
    parser.add_argument(
        "--owner-approved",
        action="store_true",
        help="Set only after the exact owner Meta publish approval phrase is present.",
    )
    parser.add_argument(
        "--approval-evidence-file",
        type=Path,
        default=None,
        help="Required with --owner-approved; must contain the exact owner approval phrase.",
    )
    parser.add_argument(
        "--tracking-qa-evidence-file",
        type=Path,
        default=None,
        help=(
            "Current LINE31 tracking/redirect QA JSON evidence; required for strict publish readiness "
            "when --owner-approved is used."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write mapping JSON to this path. Without this flag, JSON is printed to stdout.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="When --output is used, print a small machine-readable write report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.owner_approved and not args.creative_ready_declared:
            raise ValueError("--owner-approved requires --creative-ready-declared")
        if args.owner_approved and not args.approval_evidence_file:
            raise ValueError("--owner-approved requires --approval-evidence-file")
        if args.owner_approved and not args.tracking_qa_evidence_file:
            raise ValueError("--owner-approved requires --tracking-qa-evidence-file")
        mapping = build_mapping(args)
        validation_errors = _validate_prepared_mapping(mapping)
        if validation_errors:
            raise ValueError("prepared mapping failed validation: " + "; ".join(validation_errors))
        if args.output:
            _write_json(args.output, mapping, overwrite=args.overwrite)
            report = {
                "ok": True,
                "output": str(args.output),
                "creative_id": args.creative_id,
                "creative_ready_declared": args.creative_ready_declared,
                "owner_approved": args.owner_approved,
                "strict_publish_ready": args.creative_ready_declared and args.owner_approved,
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    "LINE31 creative mapping written: "
                    f"{args.output} "
                    f"(strict_publish_ready={str(report['strict_publish_ready']).lower()})"
                )
        else:
            print(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=False))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
