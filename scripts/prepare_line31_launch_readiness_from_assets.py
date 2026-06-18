#!/usr/bin/env python3
"""Prepare LINE31 launch readiness from final creative assets without publishing."""

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

from scripts.build_line31_launch_preflight_packet import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
    build_packet,
)
from scripts.prepare_line31_final_creative_mapping import (  # noqa: E402
    build_mapping,
)
from scripts.record_line31_owner_publish_approval import (  # noqa: E402
    DEFAULT_OUTPUT_DIR as DEFAULT_APPROVAL_OUTPUT_DIR,
    record_approval,
)
from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_MAPPING,
    required_owner_approval_phrase,
)
from scripts.validate_line31_launch_readiness import (  # noqa: E402
    DEFAULT_EVIDENCE_ROOT,
)

DEFAULT_APPROVAL_PHRASE_PATH = (
    DEFAULT_EVIDENCE_ROOT / "final_creative_publish_intake_and_approval.md"
)
VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".webm"}
THUMBNAIL_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def _duration_seconds(raw: str) -> float | int:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--duration-seconds must be numeric") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("--duration-seconds must be greater than 0")
    return int(value) if value.is_integer() else value


def _write_json_atomic(path: Path, data: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"output mapping exists; pass --overwrite to replace it: {path}")
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
        rendered = ", ".join(str(path.name) for path in candidates) or "none"
        raise ValueError(
            f"--asset-dir expected exactly one {label} file ({allowed}); "
            f"found {len(candidates)}: {rendered}"
        )
    return candidates[0].resolve()


def _resolve_asset_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    asset_dir = _existing_dir(args.asset_dir, "asset directory") if args.asset_dir else None
    if args.video:
        video = _existing_file(args.video, "video")
    elif asset_dir:
        video = _detect_one_asset(asset_dir, extensions=VIDEO_EXTENSIONS, label="video")
    else:
        raise ValueError("--video is required unless --asset-dir contains exactly one video file")

    if args.thumbnail:
        thumbnail = _existing_file(args.thumbnail, "thumbnail")
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


def _approval_from_existing_file(path: Path, approval_phrase_path: Path) -> dict[str, str]:
    evidence_path = _existing_file(path, "approval evidence file")
    required_phrase = required_owner_approval_phrase(approval_phrase_path)
    if required_phrase not in evidence_path.read_text(encoding="utf-8"):
        raise ValueError(
            "approval evidence file does not contain the exact required LINE31 owner approval phrase"
        )
    return {
        "approval_evidence_path": str(evidence_path),
        "approval_evidence_sha256": "",
    }


def _record_approval_evidence(args: argparse.Namespace) -> dict[str, object] | None:
    if not (args.approval_text_file or args.approval_from_stdin):
        return None
    return record_approval(
        Namespace(
            approval_text_file=args.approval_text_file,
            from_stdin=args.approval_from_stdin,
            approval_phrase_path=args.approval_phrase_path,
            mapping=args.output_mapping,
            output_dir=args.approval_output_dir,
            output=None,
            overwrite=False,
            json=False,
            require_mapping_ready=False,
        )
    )


def prepare_launch_readiness(args: argparse.Namespace) -> dict[str, Any]:
    approval_record = _record_approval_evidence(args)
    approval_evidence_file: Path | None = None
    video, thumbnail = _resolve_asset_inputs(args)

    if approval_record:
        approval_evidence_file = Path(str(approval_record["approval_evidence_path"]))
    elif args.approval_evidence_file:
        existing = _approval_from_existing_file(
            args.approval_evidence_file,
            args.approval_phrase_path,
        )
        approval_evidence_file = Path(existing["approval_evidence_path"])

    owner_approved = approval_evidence_file is not None
    if owner_approved and not args.creative_ready_declared:
        raise ValueError(
            "approval evidence requires --creative-ready-declared; do not mark publish-ready "
            "until the owner declares final creative assets ready"
        )
    if owner_approved and not args.tracking_qa_evidence_file:
        raise ValueError(
            "approval evidence requires --tracking-qa-evidence-file; strict publish readiness "
            "must prove current LINE31 tracking/redirect QA before owner-approved mapping is written"
        )

    mapping_args = Namespace(
        template=args.template,
        creative_id=args.creative_id,
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
        approval_evidence_file=approval_evidence_file,
        tracking_qa_evidence_file=args.tracking_qa_evidence_file,
        creative_ready_declared=args.creative_ready_declared,
        owner_approved=owner_approved,
    )
    mapping = build_mapping(mapping_args)

    output_mapping = args.output_mapping.expanduser().resolve()
    _write_json_atomic(output_mapping, mapping, overwrite=args.overwrite)

    manifest = build_packet(
        evidence_root=args.evidence_root,
        mapping_path=output_mapping,
        output_root=args.preflight_output_root,
        run_id=args.run_id,
        noncreative_output_root=args.noncreative_output_root,
    )
    return {
        "ok": True,
        "output_mapping": str(output_mapping),
        "resolved_video": str(video),
        "resolved_thumbnail": str(thumbnail),
        "owner_approved": owner_approved,
        "approval_evidence_path": str(approval_evidence_file or ""),
        "preflight_packet_dir": manifest["packet_dir"],
        "gate": manifest["gate"],
        "pending_ok": manifest["pending_ok"],
        "strict_ok": manifest["strict_ok"],
        "ready_to_publish": manifest["ready_to_publish"],
        "owner_source_freshness_ok": manifest.get("owner_source_freshness_ok"),
        "source_freshness_blockers": manifest.get("source_freshness_blockers", []),
        "noncreative_blockers": manifest.get("noncreative_blockers", []),
        "next_action": manifest["next_action"],
        "no_external_writes_performed": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Example: python3 scripts/prepare_line31_launch_readiness_from_assets.py "
            "--creative-id line31_countrywide_v1 --asset-dir /path/final_assets "
            "--final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 "
            "--landing-url https://acmewear.pro/line31 "
            "--kaspi-marketplace-cta-url https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/ "
            "--duration-seconds 18 --utm-placement reels --creative-ready-declared "
            "--approval-text-file /path/owner_approval.txt "
            "--tracking-qa-evidence-file /path/current_line31_tracking_redirect_qa.json "
            "--overwrite --json"
        ),
    )
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--template", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output-mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--preflight-output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--noncreative-output-root",
        type=Path,
        default=DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
        help="Output root for the current non-creative validator matrix refresh.",
    )
    parser.add_argument("--run-id", default=None)
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
    parser.add_argument("--kaspi-marketplace-cta-url", required=True)
    parser.add_argument("--duration-seconds", type=_duration_seconds, required=True)
    parser.add_argument("--utm-placement", required=True)
    parser.add_argument("--utm-content", default=None)
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--primary-cta", default="Shop now")
    parser.add_argument("--owner-notes", default="")
    parser.add_argument(
        "--creative-ready-declared",
        action="store_true",
        help="Set only after the owner declares final creative files ready.",
    )
    approval_group = parser.add_mutually_exclusive_group()
    approval_group.add_argument(
        "--approval-text-file",
        type=Path,
        help="File containing the exact owner publish approval phrase; evidence is recorded locally.",
    )
    approval_group.add_argument(
        "--approval-from-stdin",
        action="store_true",
        help="Read exact owner publish approval phrase from stdin and record evidence locally.",
    )
    approval_group.add_argument(
        "--approval-evidence-file",
        type=Path,
        help="Existing evidence file containing the exact owner publish approval phrase.",
    )
    parser.add_argument("--approval-phrase-path", type=Path, default=DEFAULT_APPROVAL_PHRASE_PATH)
    parser.add_argument("--approval-output-dir", type=Path, default=DEFAULT_APPROVAL_OUTPUT_DIR)
    parser.add_argument(
        "--tracking-qa-evidence-file",
        type=Path,
        default=None,
        help=(
            "Current LINE31 tracking/redirect QA JSON evidence; required when owner approval "
            "is supplied so strict publish cannot turn green without live QA proof."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing --output-mapping; does not overwrite approval evidence packets.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = prepare_launch_readiness(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"LINE31 launch readiness packet: {result['gate']}")
        print(result["preflight_packet_dir"])
        print(f"mapping={result['output_mapping']}")
        print(f"ready_to_publish={str(result['ready_to_publish']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
