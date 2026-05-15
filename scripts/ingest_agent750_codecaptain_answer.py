#!/usr/bin/env python3
"""Safely copy a CodeCaptain Agent750 answer into the canonical Answer folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_agent750_launch_readiness import (  # noqa: E402
    DEFAULT_DB_SHA256,
    DEFAULT_WORKBOOK_SHA256,
    REPO_ROOT,
    ReadinessResult,
    _answer_files,
    _find_decision_token,
    _is_codecaptain_answer_filename,
    check_readiness,
)
from scripts.agent750_review_pack_status import review_pack_blocking_errors  # noqa: E402
from scripts.report_agent750_next_action import (  # noqa: E402
    current_answer_search_info,
    current_review_pack_info,
    latest_completion_audit,
    latest_stopline_triage,
)


ANSWER_DIR = Path(
    "~/Docs/Oracle/Autonomous_business/2026-05-09/"
    "224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer"
)
DEFAULT_DEST_NAME = "Code_Captain_AGENT750_VALIDATE_ONLY_PLAN_REVIEW_2026-05-09.md"
DB_WORKBOOK_BOUNDARY_ERRORS = {
    "production_db_sha_mismatch",
    "protected_workbook_sha_mismatch",
    "production_db_missing",
    "protected_workbook_missing",
}
HANDOFF_ROOT = Path(
    "~/Docs/Autonomous_business_agent_handoffs/"
    "2026-05-06_codecaptain_proscope_red_recovery"
)
ORCHESTRATION_ROOT = REPO_ROOT / "runs" / "tmux_orchestration"
LIVE_REGISTRY = Path("~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json")
TMUX_VISIBILITY_KILL_SWITCH = REPO_ROOT / "config" / "tmux_orchestrator_visibility_disabled.flag"
TMUX_COMPLETION_PING_KILL_SWITCH = REPO_ROOT / "config" / "tmux_orchestrator_pings_disabled.flag"


def _latest_completion_audit_str() -> str | None:
    audit = latest_completion_audit()
    return str(audit) if audit else None


def _latest_stopline_triage_str() -> str | None:
    triage = latest_stopline_triage()
    return str(triage) if triage else None


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _destination_name(source: Path, requested: str | None) -> tuple[str, list[str]]:
    if requested:
        candidate = requested.strip()
        if not candidate or "/" in candidate or "\\" in candidate:
            return candidate, ["invalid_destination_name"]
        if not _is_codecaptain_answer_filename(Path(candidate)):
            return candidate, ["destination_name_must_match_codecaptain_markdown_pattern"]
        return candidate, []
    if _is_codecaptain_answer_filename(source):
        return source.name, []
    return DEFAULT_DEST_NAME, []


def _validate_source(source: Path) -> list[str]:
    errors: list[str] = []
    if source.name.upper().startswith("README"):
        errors.append("source_filename_reserved_for_instructions")
    if not source.exists():
        errors.append("source_file_missing")
    elif not source.is_file():
        errors.append("source_path_not_file")
    if source.suffix.lower() != ".md":
        errors.append("source_must_be_markdown")
    return errors


def _existing_answer_conflicts(answer_dir: Path, source: Path, destination: Path, *, replace: bool) -> list[str]:
    existing_answers, unexpected_files = _answer_files(answer_dir)
    errors: list[str] = []
    if unexpected_files:
        errors.append("unexpected_answer_files_present")
    if len(existing_answers) > 1:
        errors.append("multiple_existing_codecaptain_answer_files_present")

    source_resolved = source.resolve() if source.exists() else source
    destination_resolved = destination.resolve() if destination.exists() else destination
    existing_others = []
    for path in existing_answers:
        try:
            existing_resolved = path.resolve()
        except OSError:
            existing_resolved = path
        if existing_resolved not in {source_resolved, destination_resolved}:
            existing_others.append(path)
    if existing_others and not replace:
        errors.append("existing_codecaptain_answer_file_present")
    if existing_others and replace:
        errors.append("replace_would_leave_existing_codecaptain_answer_file")
    if destination.exists() and not destination.is_file():
        errors.append("destination_path_not_file")
    if destination.exists() and destination_resolved != source_resolved and not replace:
        errors.append("destination_file_exists")
    return errors


def _is_canonical_answer_dir(answer_dir: Path) -> bool:
    try:
        return answer_dir.resolve() == ANSWER_DIR.resolve()
    except OSError:
        return answer_dir == ANSWER_DIR


def _canonical_apply_boundary_readiness(answer_dir: Path) -> ReadinessResult | None:
    if not _is_canonical_answer_dir(answer_dir):
        return None
    return check_readiness(
        answer_dir=answer_dir,
        db_path=REPO_ROOT / "db" / "app.db",
        workbook_path=REPO_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx",
        expected_db_sha256=DEFAULT_DB_SHA256,
        expected_workbook_sha256=DEFAULT_WORKBOOK_SHA256,
        proof_window_lock=REPO_ROOT / "config" / "proof_window.lock",
        handoff_root=HANDOFF_ROOT,
        orchestration_root=ORCHESTRATION_ROOT,
        live_registry=LIVE_REGISTRY,
        tmux_visibility_kill_switch=TMUX_VISIBILITY_KILL_SWITCH,
        tmux_completion_ping_kill_switch=TMUX_COMPLETION_PING_KILL_SWITCH,
    )


def _boundary_errors(readiness: ReadinessResult | None) -> list[str]:
    if readiness is None:
        return []
    return sorted(set(readiness.errors) & DB_WORKBOOK_BOUNDARY_ERRORS)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dry-run by default importer for the Agent750 CodeCaptain answer")
    p.add_argument("--source", type=Path, required=True, help="Markdown answer file returned by CodeCaptain")
    p.add_argument("--answer-dir", type=Path, default=ANSWER_DIR)
    p.add_argument("--dest-name", help="Optional destination filename. Must match Code_Captain*.md or CodeCaptain*.md")
    p.add_argument("--apply", action="store_true", help="Actually copy the source file into Answer/")
    p.add_argument("--replace", action="store_true", help="Allow replacing an existing CodeCaptain answer file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.source.expanduser()
    answer_dir = args.answer_dir.expanduser()
    destination_name, name_errors = _destination_name(source, args.dest_name)
    destination = answer_dir / destination_name
    review_pack = current_review_pack_info()
    answer_search = current_answer_search_info()
    review_pack_errors = review_pack_blocking_errors(review_pack)

    errors = []
    errors.extend(name_errors)
    errors.extend(_validate_source(source))
    if review_pack_errors:
        errors.append("review_pack_unhealthy")
        errors.extend(review_pack_errors)

    decision_token = None
    if not errors:
        decision_token, token_errors = _find_decision_token([source])
        errors.extend(token_errors)
    if not errors:
        errors.extend(_existing_answer_conflicts(answer_dir, source, destination, replace=args.replace))

    if errors:
        print(
            json.dumps(
                {
                    "ok": False,
                    "errors": sorted(set(errors)),
                    "source": str(source),
                    "source_sha256": _sha256(source),
                    "answer_dir": str(answer_dir),
                    "destination": str(destination),
                    "decision_token": decision_token,
                    "applied": False,
                    "latest_completion_audit": _latest_completion_audit_str(),
                    "latest_stopline_triage": _latest_stopline_triage_str(),
                    "latest_answer_search": answer_search,
                    "review_pack": review_pack,
                    "review_pack_blocking_errors": review_pack_errors,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    action = "dry_run"
    if args.apply:
        boundary_readiness = _canonical_apply_boundary_readiness(answer_dir)
        boundary_errors = _boundary_errors(boundary_readiness)
        if boundary_errors:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "APPLY_BLOCKED_BY_DB_WORKBOOK_BOUNDARY_REVIEW",
                        "errors": boundary_errors,
                        "source": str(source),
                        "source_sha256": _sha256(source),
                        "answer_dir": str(answer_dir),
                        "destination": str(destination),
                        "decision_token": decision_token,
                        "applied": False,
                        "latest_completion_audit": _latest_completion_audit_str(),
                        "latest_stopline_triage": _latest_stopline_triage_str(),
                        "latest_answer_search": answer_search,
                        "review_pack": review_pack,
                        "review_pack_blocking_errors": review_pack_errors,
                        "boundary_readiness": asdict(boundary_readiness)
                        if boundary_readiness
                        else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2
        answer_dir.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
            action = "copied"
        else:
            action = "already_in_place"
        answer_search = current_answer_search_info()

    print(
        json.dumps(
            {
                "ok": True,
                "action": action,
                "source": str(source),
                "source_sha256": _sha256(source),
                "answer_dir": str(answer_dir),
                "destination": str(destination),
                "decision_token": decision_token,
                "applied": bool(args.apply),
                "latest_completion_audit": _latest_completion_audit_str(),
                "latest_stopline_triage": _latest_stopline_triage_str(),
                "latest_answer_search": answer_search,
                "review_pack": review_pack,
                "review_pack_blocking_errors": review_pack_errors,
                "next_command": "cd ~/Docs/Autonomous_business && ./scripts/check_agent750_launch_readiness.py",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
