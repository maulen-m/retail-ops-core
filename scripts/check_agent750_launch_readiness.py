#!/usr/bin/env python3
"""Read-only launch gate for the Agent750 -> Agents751/752/753 transition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


GREEN_TOKEN = "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE"
YELLOW_TOKEN = "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
RED_TOKEN = "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE"

DEFAULT_DB_SHA256 = "44426216a026c3ab4f7c658e4950421446b99bae99e7cf704db8e2c96d35cc91"
DEFAULT_WORKBOOK_SHA256 = "bd7c5bb3e336f0cf35423ad00e7e6f25fa5ae41cdeb3ceb51075e09047f613b9"

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DOC_ROOT = REPO_ROOT / "docs" / "parallel_runs" / "2026-05-06_codecaptain_proscope_red_recovery"
CURRENT_GATE_STATUS_PATH = RUN_DOC_ROOT / "current_gate_status_agent750_waiting_codecaptain.json"


@dataclass
class ReadinessResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    answer_files: list[str] = field(default_factory=list)
    decision_token: str | None = None
    db_sha256: str | None = None
    workbook_sha256: str | None = None
    expected_db_sha256: str | None = None
    expected_workbook_sha256: str | None = None
    db_sha256_matches_expected: bool | None = None
    workbook_sha256_matches_expected: bool | None = None
    proof_window_lock_exists: bool = False
    downstream_artifacts: list[str] = field(default_factory=list)
    unexpected_answer_files: list[str] = field(default_factory=list)
    misplaced_answer_files: list[str] = field(default_factory=list)
    live_registry: str | None = None
    live_pane_check_required: bool = False
    live_pane: str | None = None
    live_pane_identity: str | None = None
    tmux_visibility_kill_switch: str | None = None
    tmux_visibility_kill_switch_exists: bool = False
    tmux_completion_ping_kill_switch: str | None = None
    tmux_completion_ping_kill_switch_exists: bool = False
    allow_existing_downstream_artifacts: bool = False
    latest_completion_audit: str | None = None
    latest_answer_search: dict = field(default_factory=dict)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest_completion_audit() -> str | None:
    audits = sorted(RUN_DOC_ROOT.glob("ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md"))
    return str(audits[-1]) if audits else None


def _is_codecaptain_answer_filename_name(name: str) -> bool:
    return bool(re.fullmatch(r"Code_?Captain.*\.md", name, flags=re.IGNORECASE))


def _canonical_answer_folder_state(folder: object) -> tuple[list[str], list[str], str | None]:
    if not isinstance(folder, str) or not folder:
        return [], [], "canonical_answer_folder_missing_or_not_string"
    path = Path(folder)
    if not path.exists():
        return [], [], "canonical_answer_folder_missing"
    if not path.is_dir():
        return [], [], "canonical_answer_folder_not_directory"

    files: list[str] = []
    real_answer_files: list[str] = []
    for item in sorted(path.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        files.append(item.name)
        if item.name.upper().startswith("README"):
            continue
        if _is_codecaptain_answer_filename_name(item.name):
            real_answer_files.append(item.name)
    return files, real_answer_files, None


def _live_answer_search_status(real_answer_files: list[str]) -> str:
    if len(real_answer_files) == 1:
        return "REAL_AGENT750_CODECAPTAIN_ANSWER_FOUND"
    if len(real_answer_files) > 1:
        return "MULTIPLE_AGENT750_CODECAPTAIN_ANSWERS_FOUND"
    return "NO_REAL_AGENT750_CODECAPTAIN_ANSWER_FOUND"


def current_answer_search_info(status_path: Path = CURRENT_GATE_STATUS_PATH) -> dict:
    if not status_path.exists():
        return {
            "status_path": str(status_path),
            "status_path_exists": False,
            "status_path_json_valid": False,
            "status_path_error": "status_path_missing",
        }
    if not status_path.is_file():
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": False,
            "status_path_error": "status_path_not_file",
        }
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": False,
            "status_path_error": "status_json_invalid",
        }
    if not isinstance(status, dict):
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": "status_json_not_object",
        }
    answer_search = status.get("latest_answer_search")
    if not isinstance(answer_search, dict):
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": "latest_answer_search_missing_or_not_object",
        }
    payload = dict(answer_search)
    status_canonical_files = payload.get("canonical_answer_files")
    live_files, live_real_answer_files, live_error = _canonical_answer_folder_state(
        payload.get("canonical_answer_folder")
    )
    payload["canonical_answer_files_from_status"] = (
        status_canonical_files if isinstance(status_canonical_files, list) else []
    )
    if live_error is None:
        payload["canonical_answer_files"] = live_files
        payload["canonical_answer_real_files"] = live_real_answer_files
        payload["canonical_answer_files_source"] = "live_filesystem"
        payload["canonical_answer_files_match_status"] = (
            live_files == status_canonical_files
        )
        payload["status"] = _live_answer_search_status(live_real_answer_files)
    else:
        payload["canonical_answer_real_files"] = []
        payload["canonical_answer_files_source"] = "status_json"
        payload["canonical_answer_files_match_status"] = False
        payload["canonical_answer_files_live_error"] = live_error
    payload["canonical_answer_scan_observed_at_local"] = (
        datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    )
    payload["status_path"] = str(status_path)
    payload["status_path_exists"] = True
    payload["status_path_json_valid"] = True
    payload["status_path_error"] = None
    return payload


def _is_codecaptain_answer_filename(path: Path) -> bool:
    return _is_codecaptain_answer_filename_name(path.name)


def _answer_files(answer_dir: Path) -> tuple[list[Path], list[Path]]:
    if not answer_dir.exists():
        return [], []
    files = []
    unexpected = []
    for path in sorted(answer_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name.upper().startswith("README"):
            continue
        if path.name.startswith("."):
            continue
        if _is_codecaptain_answer_filename(path):
            files.append(path)
        else:
            unexpected.append(path)
    return files, unexpected


def _misplaced_answer_files(answer_dir: Path) -> list[Path]:
    """Find CodeCaptain answers saved under the review pack but outside Answer/."""
    parent = answer_dir.parent
    if not parent.exists():
        return []
    misplaced: list[Path] = []
    answer_dir_resolved = answer_dir.resolve()
    for path in sorted(parent.rglob("*")):
        if not path.is_file() or not _is_codecaptain_answer_filename(path):
            continue
        try:
            path.relative_to(answer_dir_resolved)
        except ValueError:
            misplaced.append(path)
    return misplaced


def _find_decision_token(answer_files: Iterable[Path]) -> tuple[str | None, list[str]]:
    found: list[str] = []
    tokens = (GREEN_TOKEN, YELLOW_TOKEN, RED_TOKEN)
    for path in answer_files:
        in_fenced_block = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s*```", line):
                in_fenced_block = not in_fenced_block
                continue
            if in_fenced_block:
                continue
            match = re.match(r"^\s*(decision|gate)\s*:\s*(.*?)\s*$", line, flags=re.IGNORECASE)
            if not match:
                continue
            value = match.group(2).strip().strip("`").strip()
            for token in tokens:
                if value == token and token not in found:
                    found.append(token)
    if len(found) == 1:
        return found[0], []
    if not found:
        return None, ["missing_codecaptain_decision_token"]
    return found[0], ["multiple_codecaptain_decision_tokens_found"]


def _find_downstream_artifacts(roots: Iterable[Path]) -> list[Path]:
    needles = ("agent_751", "agent_752", "agent_753", "agent751", "agent752", "agent753")
    matches: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            rel = str(path.relative_to(root)).lower()
            if any(needle in rel for needle in needles):
                matches.append(path)
    return sorted(matches)


def _validate_live_registry(registry: Path, *, skip_live_pane_check: bool) -> tuple[list[str], str | None, str | None]:
    if not registry.exists():
        return ["live_orchestrator_registry_missing"], None, None
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["live_orchestrator_registry_invalid_json"], None, None

    errors: list[str] = []
    if data.get("role") != "orchestrator_live_chat":
        errors.append("live_orchestrator_registry_wrong_role")
    pane = data.get("pane")
    if not pane:
        errors.append("live_orchestrator_registry_missing_pane")
        return errors, None, None
    if skip_live_pane_check:
        return errors, str(pane), None

    try:
        identity = subprocess.check_output(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                str(pane),
                "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_title}",
            ],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return errors + ["live_orchestrator_pane_unavailable"], str(pane), None

    fields = identity.split("\t")
    command = fields[2] if len(fields) >= 3 else ""
    if command not in {"codex", "codex-aarch64-a"}:
        errors.append("live_orchestrator_pane_not_codex")
    return errors, str(pane), identity


def check_readiness(
    *,
    answer_dir: Path,
    db_path: Path,
    workbook_path: Path,
    expected_db_sha256: str,
    expected_workbook_sha256: str,
    proof_window_lock: Path,
    handoff_root: Path,
    orchestration_root: Path,
    live_registry: Path,
    tmux_visibility_kill_switch: Path,
    tmux_completion_ping_kill_switch: Path,
    require_live_pane_check: bool = False,
    allow_existing_downstream_artifacts: bool = False,
) -> ReadinessResult:
    errors: list[str] = []

    answer_files, unexpected_answer_files = _answer_files(answer_dir)
    misplaced_answer_files = _misplaced_answer_files(answer_dir)
    if misplaced_answer_files:
        errors.append("misplaced_codecaptain_answer_files_present")
    if unexpected_answer_files:
        errors.append("unexpected_codecaptain_answer_files_present")
    if not answer_files:
        errors.append("missing_codecaptain_answer_file")
    elif len(answer_files) > 1:
        errors.append("multiple_codecaptain_answer_files_found")
    decision_token, token_errors = _find_decision_token(answer_files)
    if answer_files:
        errors.extend(token_errors)
    if decision_token == YELLOW_TOKEN:
        errors.append("codecaptain_answer_requires_fix_before_launch")
    elif decision_token == RED_TOKEN:
        errors.append("codecaptain_answer_red_stopline")
    elif decision_token not in {None, GREEN_TOKEN}:
        errors.append("codecaptain_answer_unrecognized_decision")

    db_sha = _sha256(db_path) if db_path.exists() else None
    workbook_sha = _sha256(workbook_path) if workbook_path.exists() else None
    if db_sha is None:
        errors.append("production_db_missing")
    elif db_sha != expected_db_sha256:
        errors.append("production_db_sha_mismatch")
    if workbook_sha is None:
        errors.append("protected_workbook_missing")
    elif workbook_sha != expected_workbook_sha256:
        errors.append("protected_workbook_sha_mismatch")

    proof_lock_exists = proof_window_lock.exists()
    if proof_lock_exists:
        errors.append("proof_window_lock_exists")

    tmux_visibility_kill_switch_exists = tmux_visibility_kill_switch.exists()
    if not tmux_visibility_kill_switch_exists:
        errors.append("tmux_visibility_kill_switch_missing")

    tmux_completion_ping_kill_switch_exists = tmux_completion_ping_kill_switch.exists()
    if not tmux_completion_ping_kill_switch_exists:
        errors.append("tmux_completion_ping_kill_switch_missing")

    downstream = _find_downstream_artifacts([handoff_root, orchestration_root])
    if downstream and not allow_existing_downstream_artifacts:
        errors.append("downstream_agent_artifacts_already_exist")

    live_pane = None
    live_identity = None
    if require_live_pane_check:
        registry_errors, live_pane, live_identity = _validate_live_registry(
            live_registry,
            skip_live_pane_check=False,
        )
        errors.extend(registry_errors)

    return ReadinessResult(
        ok=not errors,
        errors=errors,
        answer_files=[str(path) for path in answer_files],
        decision_token=decision_token,
        db_sha256=db_sha,
        workbook_sha256=workbook_sha,
        expected_db_sha256=expected_db_sha256,
        expected_workbook_sha256=expected_workbook_sha256,
        db_sha256_matches_expected=(
            db_sha is not None and db_sha == expected_db_sha256
        ),
        workbook_sha256_matches_expected=(
            workbook_sha is not None and workbook_sha == expected_workbook_sha256
        ),
        proof_window_lock_exists=proof_lock_exists,
        downstream_artifacts=[str(path) for path in downstream],
        unexpected_answer_files=[str(path) for path in unexpected_answer_files],
        misplaced_answer_files=[str(path) for path in misplaced_answer_files],
        live_registry=str(live_registry),
        live_pane_check_required=require_live_pane_check,
        live_pane=live_pane,
        live_pane_identity=live_identity,
        tmux_visibility_kill_switch=str(tmux_visibility_kill_switch),
        tmux_visibility_kill_switch_exists=tmux_visibility_kill_switch_exists,
        tmux_completion_ping_kill_switch=str(tmux_completion_ping_kill_switch),
        tmux_completion_ping_kill_switch_exists=tmux_completion_ping_kill_switch_exists,
        allow_existing_downstream_artifacts=allow_existing_downstream_artifacts,
        latest_completion_audit=_latest_completion_audit(),
        latest_answer_search=current_answer_search_info(),
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check Agent750 review readiness before launching Agents751/752/753")
    p.add_argument(
        "--answer-dir",
        type=Path,
        default=Path("~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer"),
    )
    p.add_argument("--db-path", type=Path, default=REPO_ROOT / "db" / "app.db")
    p.add_argument("--workbook-path", type=Path, default=REPO_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx")
    p.add_argument("--expected-db-sha256", default=DEFAULT_DB_SHA256)
    p.add_argument("--expected-workbook-sha256", default=DEFAULT_WORKBOOK_SHA256)
    p.add_argument("--proof-window-lock", type=Path, default=REPO_ROOT / "config" / "proof_window.lock")
    p.add_argument(
        "--handoff-root",
        type=Path,
        default=Path("~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery"),
    )
    p.add_argument("--orchestration-root", type=Path, default=REPO_ROOT / "runs" / "tmux_orchestration")
    p.add_argument(
        "--live-registry",
        type=Path,
        default=Path("~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json"),
    )
    p.add_argument(
        "--tmux-visibility-kill-switch",
        type=Path,
        default=REPO_ROOT / "config" / "tmux_orchestrator_visibility_disabled.flag",
    )
    p.add_argument(
        "--tmux-completion-ping-kill-switch",
        type=Path,
        default=REPO_ROOT / "config" / "tmux_orchestrator_pings_disabled.flag",
    )
    p.add_argument(
        "--require-live-pane-check",
        action="store_true",
        help="Opt-in only. Default launch readiness does not depend on human-visible LIVE pane routing.",
    )
    p.add_argument(
        "--allow-existing-downstream-artifacts",
        action="store_true",
        help=(
            "Post-launch child-agent boundary check only. Keeps reporting existing "
            "Agent751/752/753 artifacts but does not fail on them; default launch "
            "readiness remains fail-closed against downstream artifacts."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = check_readiness(**vars(args))
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
