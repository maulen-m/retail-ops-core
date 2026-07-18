#!/usr/bin/env python3
"""Report the exact next LINE31 launch action from current readiness evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_mapping import DEFAULT_MAPPING
from scripts.validate_line31_launch_readiness import (
    DEFAULT_EVIDENCE_ROOT,
    validate_launch_readiness,
)
from scripts.validate_line31_owner_objective_source_freshness import (
    DEFAULT_OWNER_FACTS_PATH,
    validate_owner_objective_source_freshness,
)


DEFAULT_APPROVAL_PATH = (
    DEFAULT_EVIDENCE_ROOT / "final_creative_publish_intake_and_approval.md"
)
DEFAULT_EXPORTS_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_CURRENT_STATUS = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_STARTER_PROMPT = (
    "Read the repo bootstrap context and execute "
    "~/Docs/Autonomous_business/docs/agent_handoffs/"
    "LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/"
    "01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md."
)
DEFAULT_ONE_SHOT_EXAMPLE = (
    "python3 scripts/prepare_line31_launch_readiness_from_assets.py "
    "--creative-id line31_countrywide_v1 "
    "--asset-dir /absolute/path/to/final_creative_drop_folder "
    "--final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 "
    "--duration-seconds 18 "
    "--utm-placement reels "
    "--landing-url 'https://acmewear.pro/line31' "
    "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
    "--creative-ready-declared "
    "--approval-phrase-path /absolute/path/to/current_sha_bound_owner_approval_phrase.txt "
    "--approval-text-file /absolute/path/to/pasted_owner_approval.txt "
    "--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json "
    "--overwrite "
    "--json"
)
DEFAULT_MAPPING_ONLY_EXAMPLE = (
    "python3 scripts/prepare_line31_final_creative_mapping.py "
    "--creative-id line31_countrywide_v1 "
    "--asset-dir /absolute/path/to/final_creative_drop_folder "
    "--final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 "
    "--duration-seconds 18 "
    "--utm-placement reels "
    "--landing-url 'https://acmewear.pro/line31' "
    "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
    "--creative-ready-declared "
    "--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json "
    "--output exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json "
    "--overwrite"
)
DEFAULT_DROP_INTAKE_COMMAND = (
    "python3 scripts/create_line31_final_creative_drop_intake.py --json"
)
DEFAULT_DROP_VALIDATOR_EXAMPLE = (
    "python3 scripts/validate_line31_final_creative_drop_intake.py "
    "--asset-dir /absolute/path/to/final_creative_drop_folder "
    "--final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 "
    "--landing-url 'https://acmewear.pro/line31' "
    "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
    "--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json "
    "--json"
)
DEFAULT_CURRENT_DROP_VALIDATOR_COMMAND = (
    "python3 scripts/validate_line31_current_final_creative_drop.py --json"
)
DEFAULT_STANDALONE_APPROVAL_RECORDER_EXAMPLE = (
    "python3 scripts/record_line31_owner_publish_approval.py "
    "--require-mapping-ready "
    "--mapping exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json "
    "--approval-phrase-path /absolute/path/to/current_sha_bound_owner_approval_phrase.txt "
    "--approval-text-file /absolute/path/to/pasted_owner_approval.txt "
    "--json"
)
DEFAULT_LAUNCH_BLOCKING_COMMANDS = [
    "python3 scripts/create_line31_final_creative_drop_intake.py --help",
    "python3 scripts/validate_line31_final_creative_drop_intake.py --help",
    "python3 scripts/validate_line31_current_final_creative_drop.py --json",
    "python3 scripts/build_line31_current_noncreative_gate_matrix.py --json",
    "python3 scripts/validate_line31_owner_objective_source_freshness.py --json",
    "python3 scripts/build_line31_launch_preflight_packet.py --json",
    "python3 scripts/audit_line31_active_goal_completion.py --json",
    "python3 scripts/write_line31_current_launch_status.py --json",
    "python3 scripts/record_line31_owner_publish_approval.py --help",
    "python3 scripts/prepare_line31_final_creative_mapping.py --help",
    "python3 scripts/prepare_line31_launch_readiness_from_assets.py --help",
    "python3 -m json.tool exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json",
    "python3 scripts/validate_line31_final_creative_mapping.py",
    "python3 scripts/validate_line31_launch_readiness.py",
]
DEFAULT_ADVISORY_REPO_HEALTH_COMMANDS = [
    "python3 scripts/validate_params.py --strict",
    "python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose",
]


def _missing_from_errors(errors: list[str]) -> list[str]:
    missing: list[str] = []
    prefix = "creative publish not ready: "
    for error in errors:
        text = error[len(prefix) :] if error.startswith(prefix) else error
        if " is required" in text:
            missing.append(text.replace(" is required", ""))
        elif "must be true" in text:
            missing.append(text)
    return sorted(set(missing))


def _noncreative_blockers_from_errors(errors: list[str]) -> list[str]:
    return sorted(
        {
            error
            for error in errors
            if error.startswith("current non-creative gate is not green-except-creative")
        }
    )


def _read_mapping_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_current_status(path: Path = DEFAULT_CURRENT_STATUS) -> dict[str, Any]:
    return _read_mapping_payload(path)


def _latest_multi_creative_mapping(exports_root: Path = DEFAULT_EXPORTS_ROOT) -> Path | None:
    candidates = sorted(
        (
            path / "final_creative_asset_mapping_3ads_pending_publish.json"
            for path in exports_root.glob("line31_final_creative_assets_*")
            if path.is_dir()
            and (path / "manifest.json").is_file()
            and (path / "final_creative_asset_mapping_3ads_pending_publish.json").is_file()
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _latest_owner_approved_bridge_mapping(exports_root: Path = DEFAULT_EXPORTS_ROOT) -> Path | None:
    candidates = sorted(
        (
            path / "final_creative_asset_mapping_3ads_owner_approved.json"
            for path in exports_root.glob("line31_meta_publish_bridge_*")
            if path.is_dir()
            and (path / "bridge_manifest.json").is_file()
            and (path / "final_creative_asset_mapping_3ads_owner_approved.json").is_file()
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _current_mapping_path(
    *,
    evidence_root: Path,
    mapping_path: Path | None,
    exports_root: Path = DEFAULT_EXPORTS_ROOT,
) -> Path:
    if mapping_path is not None:
        return mapping_path
    local_mapping = evidence_root / DEFAULT_MAPPING.name
    if evidence_root.resolve() != DEFAULT_EVIDENCE_ROOT.resolve() and local_mapping.is_file():
        return local_mapping
    if evidence_root.resolve() == DEFAULT_EVIDENCE_ROOT.resolve():
        status_mapping_raw = str(_read_current_status().get("mapping_path") or "").strip()
        if status_mapping_raw:
            status_mapping = Path(status_mapping_raw).expanduser()
            if status_mapping.is_file():
                return status_mapping
    # Fail closed on the canonical runtime path. Historical owner-approved or
    # mtime-selected mappings are evidence only and are never current authority.
    return local_mapping


def _current_sha_bound_approval_path(mapping: Path) -> Path | None:
    status = _read_current_status()
    sequence = status.get("latest_deploy_liveqa_sequence")
    if not isinstance(sequence, dict):
        return None
    raw = str(sequence.get("next_meta_publish_approval_phrase_path") or "").strip()
    if not raw:
        return None
    phrase_path = Path(raw).expanduser()
    manifest_path = phrase_path.parent / "sequence_manifest.json"
    if not phrase_path.is_file() or not manifest_path.is_file() or not mapping.is_file():
        return None
    manifest = _read_mapping_payload(manifest_path)
    manifest_mapping = Path(str(manifest.get("output_mapping") or "")).expanduser()
    if not manifest_mapping.is_file() or manifest_mapping.resolve() != mapping.resolve():
        return None
    phrase = phrase_path.read_text(encoding="utf-8").strip()
    if phrase != str(manifest.get("meta_publish_approval_phrase") or "").strip():
        return None
    if f"sha256={_sha256(mapping)}" not in phrase:
        return None
    return phrase_path


def _owner_source_freshness(
    *,
    evidence_root: Path,
    owner_facts_path: Path | None,
) -> dict[str, Any]:
    if owner_facts_path is None and evidence_root.resolve() != DEFAULT_EVIDENCE_ROOT.resolve():
        return {
            "ok": True,
            "gate": "NOT_CHECKED_CUSTOM_EVIDENCE_ROOT",
            "errors": [],
            "warnings": [],
        }
    return validate_owner_objective_source_freshness(
        owner_facts_path or DEFAULT_OWNER_FACTS_PATH
    )


def _final_assets_ready(mapping_payload: dict[str, Any]) -> bool:
    assets = mapping_payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return False
    return all(
        isinstance(row, dict)
        and row.get("video_sha256")
        and row.get("thumbnail_sha256")
        and row.get("final_asset_uri")
        and row.get("landing_url")
        for row in assets
    )


def _local_predeploy_web_green(mapping_payload: dict[str, Any]) -> bool:
    tracking = mapping_payload.get("tracking_redirect_qa")
    if not isinstance(tracking, dict):
        return False
    return (
        tracking.get("local_predeploy_gate") == "GREEN"
        and bool(tracking.get("local_predeploy_evidence_path"))
        and bool(tracking.get("local_predeploy_evidence_sha256"))
        and tracking.get("deploy_required_before_strict_green") is True
    )


def _live_tracking_green(mapping_payload: dict[str, Any]) -> bool:
    tracking = mapping_payload.get("tracking_redirect_qa")
    if not isinstance(tracking, dict):
        return False
    return (
        tracking.get("gate") == "GREEN"
        and bool(tracking.get("evidence_path"))
        and bool(tracking.get("evidence_sha256"))
    )


def build_report(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    mapping_path: Path | None = None,
    exports_root: Path = DEFAULT_EXPORTS_ROOT,
    approval_path: Path | None = None,
    owner_facts_path: Path | None = None,
) -> dict[str, Any]:
    mapping = _current_mapping_path(
        evidence_root=evidence_root,
        mapping_path=mapping_path,
        exports_root=exports_root,
    )
    mapping_payload = _read_mapping_payload(mapping)
    resolved_approval_path = approval_path or (
        _current_sha_bound_approval_path(mapping)
        if evidence_root.resolve() == DEFAULT_EVIDENCE_ROOT.resolve()
        else evidence_root / DEFAULT_APPROVAL_PATH.name
    )
    pending = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=True,
        mapping_path=mapping,
    )
    strict = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=False,
        mapping_path=mapping,
    )
    owner_source = _owner_source_freshness(
        evidence_root=evidence_root,
        owner_facts_path=owner_facts_path,
    )
    owner_source_freshness_ok = owner_source.get("ok") is True
    source_freshness_blockers = list(owner_source.get("errors", []))
    ready_to_publish = strict.ok and owner_source_freshness_ok
    noncreative_blockers = _noncreative_blockers_from_errors(
        pending.errors + strict.errors
    )

    approval_only_pending = (
        pending.ok
        and _final_assets_ready(mapping_payload)
        and _live_tracking_green(mapping_payload)
        and _missing_from_errors(strict.errors)
        == ["publish_authority.approved must be true for publish readiness"]
    )

    if ready_to_publish:
        next_action = "Run the serialized LINE31 final creative Meta publish agent after confirming exact owner approval is present."
    elif strict.ok and not owner_source_freshness_ok:
        next_action = (
            "Repair owner objective source freshness before final creative publish "
            "readiness can be trusted."
        )
    elif approval_only_pending:
        next_action = (
            "Paste the exact LINE31_COUNTRYWIDE_META_PUBLISH approval phrase, record it as "
            "approval evidence against the current 3-creative mapping, rerun Meta publish "
            "preflight, and only then execute the approved Meta API publish."
        )
    elif noncreative_blockers:
        next_action = (
            "Repair or explicitly owner-accept the retained non-creative LINE31 strict blockers "
            "before treating final creative as the only remaining launch blocker."
        )
    elif pending.ok and _final_assets_ready(mapping_payload) and _local_predeploy_web_green(mapping_payload):
        next_action = (
            "Approve and run the ACMEWEAR web deploy for the local Starry Black-first LINE31 web patch, "
            "then run post-deploy live tracking/redirect QA, wire the live GREEN QA JSON into "
            "tracking_redirect_qa, and only after that record exact owner Meta publish approval."
        )
    elif pending.ok and _final_assets_ready(mapping_payload):
        next_action = (
            "Final creative assets are staged; verify current tracking/redirect QA, wire the "
            "GREEN QA evidence into tracking_redirect_qa, then record exact owner approval evidence."
        )
    elif pending.ok:
        next_action = (
            "Use the one-shot final-assets readiness helper when creative files are ready, "
            "then verify current tracking/redirect QA, strict validators, and exact owner approval evidence."
        )
    else:
        next_action = "Repair non-creative LINE31 readiness blockers before preparing publish."

    return {
        "status": (
            "READY_TO_PUBLISH"
            if ready_to_publish
            else (
                "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
                if strict.ok and not owner_source_freshness_ok
                else pending.gate
            )
        ),
        "ready_to_publish": ready_to_publish,
        "pending_gate_ok": pending.ok,
        "pending_gate": pending.gate,
        "strict_gate_ok": strict.ok,
        "strict_gate": strict.gate,
        "missing_or_pending": sorted(
            set(
                _missing_from_errors(strict.errors)
                + ([] if resolved_approval_path else ["current SHA-bound owner approval phrase"])
            )
        ),
        "noncreative_blockers": noncreative_blockers,
        "owner_source_freshness_ok": owner_source_freshness_ok,
        "owner_source_freshness_gate": owner_source.get("gate", ""),
        "source_freshness_blockers": source_freshness_blockers,
        "warnings": sorted(set(pending.warnings + strict.warnings)),
        "next_action": next_action,
        "final_assets_ready": _final_assets_ready(mapping_payload),
        "local_predeploy_web_green": _local_predeploy_web_green(mapping_payload),
        "live_tracking_green": _live_tracking_green(mapping_payload),
        "mapping_path": str(mapping),
        "mapping_helper": "python3 scripts/prepare_line31_final_creative_mapping.py",
        "one_shot_readiness_helper": (
            "python3 scripts/prepare_line31_launch_readiness_from_assets.py"
        ),
        "one_shot_example_command": DEFAULT_ONE_SHOT_EXAMPLE,
        "mapping_only_example_command": DEFAULT_MAPPING_ONLY_EXAMPLE,
        "drop_intake_helper": "python3 scripts/create_line31_final_creative_drop_intake.py",
        "drop_intake_command": DEFAULT_DROP_INTAKE_COMMAND,
        "drop_validator_helper": "python3 scripts/validate_line31_final_creative_drop_intake.py",
        "drop_validator_example_command": DEFAULT_DROP_VALIDATOR_EXAMPLE,
        "current_drop_validator_helper": "python3 scripts/validate_line31_current_final_creative_drop.py",
        "current_drop_validator_command": DEFAULT_CURRENT_DROP_VALIDATOR_COMMAND,
        "approval_phrase_path": str(resolved_approval_path or ""),
        "approval_evidence_requirement": (
            "Before publish, save the exact owner approval phrase in a separate evidence file "
            "and reference it from publish_authority.approval_evidence_path with matching SHA-256. "
            "Strict publish also requires a current tracking/redirect QA JSON evidence file with "
            "matching tracking_redirect_qa.evidence_sha256. "
            "For the standalone/manual route, use --require-mapping-ready so approval evidence "
            "cannot be recorded against a placeholder creative mapping."
        ),
        "standalone_approval_recorder": "python3 scripts/record_line31_owner_publish_approval.py",
        "standalone_approval_recorder_example_command": (
            "python3 scripts/record_line31_owner_publish_approval.py "
            "--require-mapping-ready "
            f"--mapping {mapping} "
            f"--approval-phrase-path {resolved_approval_path or '/absolute/path/to/current_sha_bound_owner_phrase.txt'} "
            "--approval-text-file /absolute/path/to/pasted_owner_approval.txt "
            "--json"
        ),
        "standalone_approval_guard": (
            "Use the standalone recorder only after final creative mapping is filled. "
            "The mapping must also include current tracking/redirect QA evidence. "
            "It must reject a placeholder creative mapping. "
            "The one-shot helper can record approval while generating the mapping because "
            "it validates the produced mapping immediately."
        ),
        "starter_prompt": DEFAULT_STARTER_PROMPT,
        "commands_to_close": DEFAULT_LAUNCH_BLOCKING_COMMANDS,
        "advisory_repo_health_commands": DEFAULT_ADVISORY_REPO_HEALTH_COMMANDS,
        "internal_kaspi_policy": "KEEP_INTERNAL_KASPI_LINE31_CAMPAIGNS_ON_UNTIL_SEPARATE_OWNER_APPROVAL",
    }


def _print_markdown(report: dict[str, Any]) -> None:
    print(f"# LINE31 Next Launch Action\n")
    print(f"Status: `{report['status']}`")
    print(f"Ready to publish: `{str(report['ready_to_publish']).lower()}`")
    print()
    print("## Next Action")
    print()
    print(report["next_action"])
    print()
    if report["missing_or_pending"]:
        print("## Missing Or Pending")
        print()
        for item in report["missing_or_pending"]:
            print(f"- `{item}`")
        print()
    if report["noncreative_blockers"]:
        print("## Non-Creative Blockers")
        print()
        for item in report["noncreative_blockers"]:
            print(f"- {item}")
        print()
    if report["source_freshness_blockers"]:
        print("## Source Freshness Blockers")
        print()
        for item in report["source_freshness_blockers"]:
            print(f"- {item}")
        print()
    print("## Paths")
    print()
    print(f"- Mapping: `{report['mapping_path']}`")
    print(f"- Mapping helper: `{report['mapping_helper']}`")
    print(f"- One-shot readiness helper: `{report['one_shot_readiness_helper']}`")
    print(f"- Approval phrase: `{report['approval_phrase_path']}`")
    print(f"- Approval evidence: {report['approval_evidence_requirement']}")
    print()
    print("## Preferred One-Shot Command")
    print()
    print("```bash")
    print(report["one_shot_example_command"])
    print("```")
    if report.get("advisory_repo_health_commands"):
        print()
        print("## Advisory Repo Health Commands")
        print()
        print("These are visible broader Autonomous_business health checks, but they are not LINE31 launch-blocking when the current non-creative matrix records them as advisory.")
        print()
        print("```bash")
        for command in report["advisory_repo_health_commands"]:
            print(command)
        print("```")
    print()
    print("## Drop-Intake Folder Command")
    print()
    print("```bash")
    print(report["drop_intake_command"])
    print("```")
    print()
    print("## Drop-Intake Validator Command")
    print()
    print("```bash")
    print(report["drop_validator_example_command"])
    print("```")
    print()
    print("## Current Pointer Drop Validator")
    print()
    print("Use this after refreshing `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`; it validates the latest drop folder from the stable pointer.")
    print()
    print("```bash")
    print(report["current_drop_validator_command"])
    print("```")
    print()
    print("## Mapping-Only Command")
    print()
    print("```bash")
    print(report["mapping_only_example_command"])
    print("```")
    print()
    print("## Standalone Approval Recorder Command")
    print()
    print("Use only after the final creative mapping is filled. The one-shot helper is preferred when final video, thumbnail, and owner approval text arrive together.")
    print()
    print("```bash")
    print(report["standalone_approval_recorder_example_command"])
    print("```")
    print()
    print("## Starter Prompt")
    print()
    print("```text")
    print(report["starter_prompt"])
    print("```")
    print()
    print("## Commands To Close")
    print()
    print("```bash")
    for command in report["commands_to_close"]:
        print(command)
    print("```")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--mapping", type=Path, default=None)
    parser.add_argument("--approval-path", type=Path, default=None)
    parser.add_argument("--owner-facts-path", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        evidence_root=args.evidence_root,
        mapping_path=args.mapping,
        approval_path=args.approval_path,
        owner_facts_path=args.owner_facts_path,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_markdown(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
