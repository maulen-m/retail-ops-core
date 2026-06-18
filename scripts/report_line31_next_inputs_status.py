#!/usr/bin/env python3
"""Report which LINE31 launch inputs are present before final publish readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_current_final_creative_drop import (  # noqa: E402
    DEFAULT_STATUS_PATH,
    _load_json,
    _latest_drop,
)

DEFAULT_EXPERT_ANSWER_DIR = Path(
    "~/Docs/Oracle/Autonomous_business/2026-06-01/"
    "211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer"
)
DEFAULT_POST_EXPERT_ADDENDUM = (
    PROJECT_ROOT
    / "docs"
    / "validation"
    / "LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md"
)
DEFAULT_NEXT_INPUTS_DOC = (
    PROJECT_ROOT / "docs" / "current" / "LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md"
)
STRICT_OWNER_STATUS = "YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA"
VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".webm"}
THUMBNAIL_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def _files(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(p for p in path.rglob("*") if p.is_file())


def _direct_files(path: Path, extensions: set[str]) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(
        p
        for p in path.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )


def _latest_multi_assets(current_status: dict[str, Any]) -> dict[str, Any]:
    latest = current_status.get("latest_final_creative_assets")
    if not isinstance(latest, dict) or not latest.get("exists"):
        return {"exists": False, "dir": "", "manifest": "", "assets": []}
    manifest_path = latest.get("manifest")
    if not manifest_path:
        return {"exists": False, "dir": latest.get("dir", ""), "manifest": "", "assets": []}
    manifest = Path(str(manifest_path))
    if not manifest.exists() or not manifest.is_file():
        return {"exists": False, "dir": latest.get("dir", ""), "manifest": str(manifest), "assets": []}
    payload = _load_json(manifest)
    assets = payload.get("assets")
    return {
        "exists": isinstance(assets, list) and bool(assets),
        "dir": latest.get("dir", ""),
        "manifest": str(manifest),
        "assets": assets if isinstance(assets, list) else [],
        "payload": payload,
    }


def _text_non_placeholder(path: Path | None) -> bool:
    if not path or not path.exists() or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return bool(text) and "Paste the exact LINE31 owner Meta publish approval phrase here" not in text


def _expert_answer_integrated(*, addendum_path: Path, next_inputs_doc: Path) -> bool:
    if not addendum_path.exists() or not next_inputs_doc.exists():
        return False
    addendum = addendum_path.read_text(encoding="utf-8", errors="replace")
    next_inputs = next_inputs_doc.read_text(encoding="utf-8", errors="replace")
    return (
        STRICT_OWNER_STATUS in addendum
        and "LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md" in next_inputs
        and "Expert answer file:" in next_inputs
    )


def build_status(
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
    expert_answer_dir: Path = DEFAULT_EXPERT_ANSWER_DIR,
    post_expert_addendum_path: Path = DEFAULT_POST_EXPERT_ADDENDUM,
    next_inputs_doc_path: Path = DEFAULT_NEXT_INPUTS_DOC,
) -> dict[str, Any]:
    current_status = _load_json(status_path)
    latest_drop = _latest_drop(current_status)
    multi_assets = _latest_multi_assets(current_status)
    asset_dir = Path(str(multi_assets["dir"] or latest_drop["asset_dir"]))
    approval_file = (
        Path(str(latest_drop["approval_text_file"]))
        if latest_drop.get("approval_text_file")
        else None
    )
    expert_files = _files(expert_answer_dir)
    videos: list[Path]
    thumbnails: list[Path]
    if multi_assets["exists"]:
        videos = [
            Path(str(row.get("local_video_path")))
            for row in multi_assets["assets"]
            if isinstance(row, dict) and row.get("local_video_path")
        ]
        thumbnails = [
            Path(str(row.get("thumbnail_path")))
            for row in multi_assets["assets"]
            if isinstance(row, dict) and row.get("thumbnail_path")
        ]
    else:
        videos = _direct_files(asset_dir, VIDEO_EXTENSIONS)
        thumbnails = _direct_files(asset_dir, THUMBNAIL_EXTENSIONS)
    approval_text_present = _text_non_placeholder(approval_file)
    expert_answer_integrated = bool(expert_files) and _expert_answer_integrated(
        addendum_path=post_expert_addendum_path,
        next_inputs_doc=next_inputs_doc_path,
    )
    exactly_one_video = len(videos) == 1
    exactly_one_thumbnail = len(thumbnails) == 1
    multi_asset_ready = multi_assets["exists"] and len(videos) == len(thumbnails) >= 1
    assets_present = multi_asset_ready or (exactly_one_video and exactly_one_thumbnail)
    ambiguous_assets = (len(videos) > 1 or len(thumbnails) > 1) and not multi_asset_ready

    if ambiguous_assets:
        next_gate = "AMBIGUOUS_CREATIVE_ASSETS"
        next_action = (
            "Clean the final-assets folder or pass explicit --video and --thumbnail paths "
            "before mapping."
        )
    elif multi_asset_ready and not approval_text_present:
        next_gate = "FINAL_MULTI_CREATIVES_STAGED_PENDING_TRACKING_QA_AND_OWNER_APPROVAL"
        next_action = (
            "Run current tracking/redirect QA, provide exact owner approval evidence, "
            "then record publish approval. Strict publish remains YELLOW until both are present."
        )
    elif assets_present and approval_text_present:
        next_gate = "READY_FOR_ONE_SHOT_LOCAL_BRIDGE"
        next_action = "Run prepare_line31_launch_readiness_from_assets.py with real URLs and approval evidence."
    elif assets_present:
        next_gate = "READY_FOR_FINAL_URLS_AND_OWNER_APPROVAL"
        next_action = "Provide final asset URI, final Kaspi CTA URL, and exact owner approval evidence."
    elif expert_answer_integrated:
        next_gate = "POST_EXPERT_INTEGRATED_WAITING_FOR_FINAL_CREATIVE"
        next_action = (
            "Provide final video, thumbnail, real URLs, exact owner approval evidence, "
            "and current tracking/redirect QA; strict publish remains YELLOW."
        )
    elif expert_files:
        next_gate = "READY_TO_INGEST_EXPERT_ANSWER"
        next_action = "Ingest the external expert answer against current status, audit, preflight, and matrix."
    else:
        next_gate = "WAITING_FOR_EXPERT_ANSWER_OR_FINAL_CREATIVE"
        next_action = "Wait for external expert answer or final video plus thumbnail."

    return {
        "ok": not ambiguous_assets,
        "gate": next_gate,
        "next_action": next_action,
        "current_status": current_status.get("status"),
        "current_status_path": str(status_path.expanduser().resolve()),
        "current_status_generated_at": current_status.get("generated_at", ""),
        "strict_gate": current_status.get("strict_gate"),
        "ready_to_publish": current_status.get("ready_to_publish"),
        "expert_answer_dir": str(expert_answer_dir),
        "expert_answer_file_count": len(expert_files),
        "expert_answer_files": [str(p) for p in expert_files[:20]],
        "expert_answer_integrated": expert_answer_integrated,
        "post_expert_addendum_path": str(post_expert_addendum_path),
        "owner_facing_publish_status": STRICT_OWNER_STATUS,
        "asset_dir": str(asset_dir),
        "video_count": len(videos),
        "thumbnail_count": len(thumbnails),
        "video_files": [str(p) for p in videos],
        "thumbnail_files": [str(p) for p in thumbnails],
        "approval_text_file": str(approval_file or ""),
        "approval_text_present": approval_text_present,
        "latest_drop_checklist_path": latest_drop.get("checklist_path", ""),
        "latest_multi_asset_manifest": multi_assets.get("manifest", ""),
        "latest_multi_asset_gate": (multi_assets.get("payload") or {}).get("gate", ""),
        "one_shot_command": latest_drop.get("one_shot_command", ""),
        "no_external_writes_performed": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--expert-answer-dir", type=Path, default=DEFAULT_EXPERT_ANSWER_DIR)
    parser.add_argument("--post-expert-addendum", type=Path, default=DEFAULT_POST_EXPERT_ADDENDUM)
    parser.add_argument("--next-inputs-doc", type=Path, default=DEFAULT_NEXT_INPUTS_DOC)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = build_status(
            status_path=args.status_path,
            expert_answer_dir=args.expert_answer_dir,
            post_expert_addendum_path=args.post_expert_addendum,
            next_inputs_doc_path=args.next_inputs_doc,
        )
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
        print(f"Next action: {payload['next_action']}")
        print(f"Expert answer files: {payload['expert_answer_file_count']}")
        print(f"Videos: {payload['video_count']}; thumbnails: {payload['thumbnail_count']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
