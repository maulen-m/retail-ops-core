#!/usr/bin/env python3
"""Create the no-write bridge from LINE31 approval evidence to Meta API publish."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_STATUS = PROJECT_ROOT / "docs/current/LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation"
FACEBOOK_ADS_ROOT = Path("~/Docs/Business_3/Facebook_ads")


class BridgeError(RuntimeError):
    """Raised when the bridge cannot be built safely."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BridgeError(f"{path} root must be a JSON object")
    return payload


def _run_id() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _shell(value: Path | str) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\\''") + "'"


def _required_path(path: str | None, label: str) -> Path:
    if not path:
        raise BridgeError(f"{label} is missing")
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise BridgeError(f"{label} does not exist: {resolved}")
    return resolved


def _sequence_payload(status: dict[str, Any]) -> dict[str, Any]:
    sequence = status.get("latest_deploy_liveqa_sequence")
    if not isinstance(sequence, dict):
        raise BridgeError("current status is missing latest_deploy_liveqa_sequence")
    manifest = _required_path(str(sequence.get("manifest") or ""), "deploy/live-QA sequence manifest")
    return _read_json(manifest)


def build_bridge(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status.expanduser().resolve()
    status = _read_json(status_path)
    sequence = _sequence_payload(status)

    output_dir = args.output_root / f"line31_meta_publish_bridge_{args.run_id or _run_id()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = _required_path(str(sequence.get("output_mapping") or status.get("mapping_path") or ""), "current mapping")
    asset_manifest = _required_path(str(sequence.get("asset_manifest") or ""), "asset manifest")
    live_qa = _required_path(str((sequence.get("live_qa") or {}).get("path") or ""), "live QA evidence")
    next_phrase_source = _required_path(
        str((status.get("latest_deploy_liveqa_sequence") or {}).get("next_meta_publish_approval_phrase_path") or ""),
        "next LINE31 Meta approval phrase",
    )

    required_phrase_copy = output_dir / "REQUIRED_EXACT_LINE31_META_PUBLISH_APPROVAL_PHRASE.txt"
    shutil.copyfile(next_phrase_source, required_phrase_copy)

    owner_paste_file = output_dir / "OWNER_PASTED_EXACT_LINE31_META_PUBLISH_APPROVAL.txt"
    owner_approval_evidence = output_dir / "owner_publish_approval_evidence.md"
    approved_mapping = output_dir / "final_creative_asset_mapping_3ads_owner_approved.json"
    meta_write_approval_file = output_dir / "OWNER_PASTED_EXACT_META_API_LIVE_WRITE_APPROVAL.txt"

    commands = {
        "record_line31_owner_publish_approval": (
            "cd ~/Docs/Autonomous_business && "
            "python3 scripts/record_line31_owner_publish_approval.py "
            f"--approval-phrase-path {_shell(required_phrase_copy)} "
            f"--approval-text-file {_shell(owner_paste_file)} "
            f"--mapping {_shell(mapping)} "
            "--require-mapping-ready "
            f"--output {_shell(owner_approval_evidence)} "
            "--json"
        ),
        "write_owner_approved_mapping": (
            "cd ~/Docs/Autonomous_business && "
            "python3 scripts/prepare_line31_multi_creative_mapping.py "
            f"--asset-manifest {_shell(asset_manifest)} "
            "--landing-url https://acmewear.pro/line31 "
            "--kaspi-marketplace-cta-url https://acmewear.pro/go/starry-black "
            "--creative-ready-declared "
            "--owner-approved "
            f"--approval-phrase-path {_shell(required_phrase_copy)} "
            f"--approval-evidence-file {_shell(owner_approval_evidence)} "
            f"--tracking-qa-evidence-file {_shell(live_qa)} "
            f"--output {_shell(approved_mapping)} "
            "--overwrite --json"
        ),
        "validate_owner_approved_mapping": (
            "cd ~/Docs/Autonomous_business && "
            f"python3 scripts/validate_line31_launch_readiness.py --mapping {_shell(approved_mapping)} --json"
        ),
        "green_meta_publish_preflight_no_write": (
            "cd ~/Docs/Business_3/Facebook_ads && "
            "PYTHONPATH=. python3 scripts/preflight_line31_countrywide_meta_publish.py "
            f"--mapping {_shell(approved_mapping)} --json"
        ),
        "execute_meta_publish_after_exact_meta_api_live_write_approval": (
            "cd ~/Docs/Business_3/Facebook_ads && "
            "PYTHONPATH=. python3 scripts/preflight_line31_countrywide_meta_publish.py "
            f"--mapping {_shell(approved_mapping)} "
            f"--approval-text-file {_shell(meta_write_approval_file)} "
            "--execute-approved-meta-publish --json"
        ),
    }

    sequence_gate = str(sequence.get("gate") or "")
    mapping_validation = sequence.get("mapping_validation")
    bridge_ready = (
        sequence_gate == "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE"
        and isinstance(mapping_validation, dict)
        and mapping_validation.get("expected_pending_meta_approval_only") is True
    )
    gate = (
        "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE"
        if bridge_ready
        else "YELLOW_LINE31_META_APPROVAL_BRIDGE_REVIEW_REQUIRED_NO_WRITE"
    )
    payload = {
        "gate": gate,
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "status_path": str(status_path),
        "sequence_gate": sequence_gate,
        "mapping": str(mapping),
        "asset_manifest": str(asset_manifest),
        "live_qa": str(live_qa),
        "required_line31_meta_publish_phrase_source": str(next_phrase_source),
        "required_line31_meta_publish_phrase_copy": str(required_phrase_copy),
        "owner_paste_file": str(owner_paste_file),
        "owner_approval_evidence": str(owner_approval_evidence),
        "owner_approved_mapping": str(approved_mapping),
        "meta_api_live_write_approval_file": str(meta_write_approval_file),
        "commands": commands,
        "two_stage_approval_boundary": [
            "Stage 1 records the exact LINE31_COUNTRYWIDE_META_PUBLISH owner approval and makes the mapping strict-ready.",
            "Stage 2 runs Meta publish preflight, which generates a separate exact META_API_LIVE_WRITE phrase.",
            "Stage 3 executes Graph API writes only after that exact META_API_LIVE_WRITE phrase is pasted into the approval file.",
        ],
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "output_dir": str(output_dir),
    }
    (output_dir / "bridge_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "closeout.md").write_text(_render_closeout(payload), encoding="utf-8")
    return payload


def _render_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Meta Publish Bridge",
        "",
        f"Gate: {payload['gate']}",
        "",
        "## Boundary",
        "",
        "- External write attempted: `False`",
        "- Meta write attempted: `False`",
        "- This packet plans the approval-to-publish sequence only.",
        "",
        "## Stage Boundary",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["two_stage_approval_boundary"])
    lines.extend(
        [
            "",
            "## Required Owner Phrase To Paste First",
            "",
            f"`{payload['required_line31_meta_publish_phrase_copy']}`",
            "",
            "## Commands",
            "",
        ]
    )
    for name, command in payload["commands"].items():
        lines.extend([f"### {name}", "", "```bash", command, "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_bridge(args)
    except BridgeError as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
