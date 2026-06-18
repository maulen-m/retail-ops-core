#!/usr/bin/env python3
"""Prepare a LINE31 final creative mapping from a staged multi-asset manifest."""

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


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return payload


def _load_template(path: Path) -> dict[str, Any]:
    return _load_json(_existing_file(path, "template"))


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


def _status(*, creative_ready: bool, owner_approved: bool) -> str:
    if creative_ready and owner_approved:
        return "FINAL_CREATIVE_READY_OWNER_APPROVED_MULTI_ASSET"
    if creative_ready:
        return "FINAL_CREATIVE_READY_PENDING_OWNER_APPROVAL_MULTI_ASSET"
    return "FINAL_CREATIVE_MAPPING_DRAFT_PENDING_CREATIVE_READY_DECLARATION_MULTI_ASSET"


def _manifest_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("asset manifest must contain a non-empty assets list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(assets):
        if not isinstance(raw, dict):
            raise ValueError(f"manifest assets[{index}] must be an object")
        creative_id = str(raw.get("creative_id") or "").strip()
        if not creative_id:
            raise ValueError(f"manifest assets[{index}].creative_id is required")
        if creative_id in seen:
            raise ValueError(f"manifest assets[{index}].creative_id duplicates {creative_id}")
        seen.add(creative_id)
        normalized.append(raw)
    return normalized


def _optional_tracking_qa(path: Path | None) -> tuple[str, str]:
    if not path:
        return "", ""
    resolved = _existing_file(path, "tracking/redirect QA evidence file")
    return str(resolved), _sha256(resolved)


def _approval_evidence(
    *,
    owner_approved: bool,
    approval_evidence_file: Path | None,
    approval_phrase_path: str,
) -> tuple[str, str]:
    if not owner_approved:
        return "", ""
    if not approval_evidence_file:
        raise ValueError("--owner-approved requires --approval-evidence-file")
    resolved = _existing_file(approval_evidence_file, "approval evidence file")
    required_phrase = required_owner_approval_phrase(Path(approval_phrase_path))
    if required_phrase not in resolved.read_text(encoding="utf-8"):
        raise ValueError(
            "approval evidence file does not contain the exact required owner approval phrase"
        )
    return str(resolved), _sha256(resolved)


def _coalesce_asset_uri(
    *,
    final_asset_base_url: str,
    creative_id: str,
    local_video_path: Path,
) -> str:
    base = final_asset_base_url.strip().rstrip("/")
    if not base:
        return str(local_video_path)
    suffix = local_video_path.name
    return f"{base}/{suffix}" if "{creative_id}" not in base else base.format(creative_id=creative_id)


def build_mapping(args: argparse.Namespace) -> dict[str, Any]:
    template = _load_template(args.template)
    manifest_path = _existing_file(args.asset_manifest, "asset manifest")
    manifest = _load_json(manifest_path)
    assets = _manifest_assets(manifest)
    tracking_path, tracking_sha = _optional_tracking_qa(args.tracking_qa_evidence_file)
    approval_path, approval_sha = _approval_evidence(
        owner_approved=args.owner_approved,
        approval_evidence_file=args.approval_evidence_file,
        approval_phrase_path=args.approval_phrase_path,
    )

    mapped_assets: list[dict[str, Any]] = []
    for raw in assets:
        creative_id = str(raw["creative_id"]).strip()
        local_video = _existing_file(Path(str(raw.get("local_video_path") or "")), "local video")
        thumbnail = _existing_file(Path(str(raw.get("thumbnail_path") or "")), "thumbnail")
        utm_content = str(raw.get("utm_content") or creative_id).strip()
        utm_placement = str(raw.get("utm_placement") or args.utm_placement).strip()
        mapped_assets.append(
            {
                "creative_id": creative_id,
                "local_file_path": str(local_video),
                "final_asset_uri": _coalesce_asset_uri(
                    final_asset_base_url=args.final_asset_base_url,
                    creative_id=creative_id,
                    local_video_path=local_video,
                ),
                "thumbnail_path_or_uri": str(thumbnail),
                "video_sha256": str(raw.get("video_sha256") or _sha256(local_video)),
                "thumbnail_sha256": str(raw.get("thumbnail_sha256") or _sha256(thumbnail)),
                "aspect_ratio": args.aspect_ratio,
                "duration_seconds": raw.get("duration_seconds"),
                "language": str(raw.get("language") or args.language),
                "primary_cta": str(raw.get("primary_cta") or args.primary_cta),
                "landing_url": _normalize_landing_url(
                    args.landing_url,
                    utm_content=utm_content,
                    utm_placement=utm_placement,
                ),
                "utm_content": utm_content,
                "utm_placement": utm_placement,
                "kaspi_marketplace_cta_url": args.kaspi_marketplace_cta_url,
                "owner_notes": args.owner_notes,
            }
        )

    return {
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
            "gate": "GREEN" if tracking_path else "",
            "evidence_path": tracking_path,
            "evidence_sha256": tracking_sha,
            "refresh_policy": (
                "Refresh after final landing URL, UTM, /go/:color route, or website deploy changes; "
                "strict publish readiness cannot pass without this current local evidence hash."
            ),
        },
        "assets": mapped_assets,
        "publish_authority": {
            "owner_approval_required": True,
            "approval_phrase_path": args.approval_phrase_path,
            "approved": args.owner_approved,
            "approval_evidence_path": approval_path,
            "approval_evidence_sha256": approval_sha,
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
        "multi_asset_source_manifest": {
            "path": str(manifest_path),
            "sha256": _sha256(manifest_path),
            "assets_count": len(mapped_assets),
            "campaign_shape": manifest.get("campaign_shape", {}),
            "landing_cta_priority": manifest.get("landing_cta_priority", []),
        },
    }


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


def _allowed_pending_errors(mapping: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    if not mapping.get("creative_ready_declaration_received"):
        allowed.add("creative_ready_declaration_received must be true for publish readiness")
    publish = mapping.get("publish_authority") or {}
    if not publish.get("approved"):
        allowed.add("publish_authority.approved must be true for publish readiness")
    tracking = mapping.get("tracking_redirect_qa") or {}
    if not tracking.get("evidence_path"):
        allowed.update(
            {
                "tracking_redirect_qa.gate is required",
                "tracking_redirect_qa.evidence_path is required",
                "tracking_redirect_qa.evidence_sha256 is required",
            }
        )
    return allowed


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

    allowed_errors = _allowed_pending_errors(mapping)
    return [error for error in result.errors if error not in allowed_errors]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Example: python3 scripts/prepare_line31_multi_creative_mapping.py "
            "--asset-manifest exports/validation/line31_final_creative_assets_YYYYMMDD_HHMMSS/manifest.json "
            "--landing-url 'https://acmewear.pro/line31' "
            "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
            "--creative-ready-declared --output exports/validation/.../final_creative_asset_mapping_3ads.json"
        ),
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--asset-manifest", type=Path, required=True)
    parser.add_argument("--landing-url", required=True)
    parser.add_argument(
        "--kaspi-marketplace-cta-url",
        required=True,
        help="Final marketplace CTA URL used from the landing page.",
    )
    parser.add_argument(
        "--final-asset-base-url",
        default="",
        help=(
            "Optional remote base URL for final video assets. If omitted, the local staged video "
            "path is used so hash-backed local preflight can stay strict-yellow before upload."
        ),
    )
    parser.add_argument("--utm-placement", default="reels")
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--primary-cta", default="open_line31_landing")
    parser.add_argument("--owner-notes", default="")
    parser.add_argument("--approval-phrase-path", default=DEFAULT_APPROVAL_PATH)
    parser.add_argument("--creative-ready-declared", action="store_true")
    parser.add_argument("--owner-approved", action="store_true")
    parser.add_argument("--approval-evidence-file", type=Path, default=None)
    parser.add_argument("--tracking-qa-evidence-file", type=Path, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.owner_approved and not args.creative_ready_declared:
            raise ValueError("--owner-approved requires --creative-ready-declared")
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
                "assets_count": len(mapping["assets"]),
                "creative_ready_declared": args.creative_ready_declared,
                "owner_approved": args.owner_approved,
                "strict_publish_ready": args.creative_ready_declared and args.owner_approved,
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    "LINE31 multi-creative mapping written: "
                    f"{args.output} "
                    f"(assets={len(mapping['assets'])}, "
                    f"strict_publish_ready={str(report['strict_publish_ready']).lower()})"
                )
        else:
            print(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=False))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
