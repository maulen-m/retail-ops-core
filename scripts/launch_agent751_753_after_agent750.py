#!/usr/bin/env python3
"""Guarded launcher for Agents751/752/753 after Agent750 CodeCaptain approval."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_agent750_launch_readiness import (
    DEFAULT_DB_SHA256,
    DEFAULT_WORKBOOK_SHA256,
    GREEN_TOKEN,
    REPO_ROOT,
    check_readiness,
    current_answer_search_info,
)
from scripts.agent750_review_pack_status import (
    review_pack_blocking_errors,
    review_pack_info_from_status,
)


TMUX_LAUNCHER = Path("~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py")
RUN_DOC_ROOT = REPO_ROOT / "docs" / "parallel_runs" / "2026-05-06_codecaptain_proscope_red_recovery"
STARTER_FOLDER = RUN_DOC_ROOT / "starter_prompts"
CURRENT_GATE_STATUS_PATH = RUN_DOC_ROOT / "current_gate_status_agent750_waiting_codecaptain.json"
ANSWER_DIR = Path(
    "~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer"
)
HANDOFF_ROOT = Path("~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery")
LIVE_REGISTRY = Path("~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json")


def run_readiness_check():
    return check_readiness(
        answer_dir=ANSWER_DIR,
        db_path=REPO_ROOT / "db" / "app.db",
        workbook_path=REPO_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx",
        expected_db_sha256=DEFAULT_DB_SHA256,
        expected_workbook_sha256=DEFAULT_WORKBOOK_SHA256,
        proof_window_lock=REPO_ROOT / "config" / "proof_window.lock",
        handoff_root=HANDOFF_ROOT,
        orchestration_root=REPO_ROOT / "runs" / "tmux_orchestration",
        live_registry=LIVE_REGISTRY,
        tmux_visibility_kill_switch=REPO_ROOT / "config" / "tmux_orchestrator_visibility_disabled.flag",
        tmux_completion_ping_kill_switch=REPO_ROOT / "config" / "tmux_orchestrator_pings_disabled.flag",
        require_live_pane_check=False,
    )


def _current_review_pack_info() -> dict:
    return review_pack_info_from_status(CURRENT_GATE_STATUS_PATH)


def _current_answer_search_info() -> dict:
    return current_answer_search_info(CURRENT_GATE_STATUS_PATH)


def _latest_completion_audit() -> str | None:
    if CURRENT_GATE_STATUS_PATH.exists():
        try:
            status = json.loads(CURRENT_GATE_STATUS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        if isinstance(status, dict):
            audit = status.get("latest_completion_audit")
            if audit:
                return str(audit)
    audits = sorted(RUN_DOC_ROOT.glob("ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md"))
    return str(audits[-1]) if audits else None


def _latest_stopline_triage() -> str | None:
    if CURRENT_GATE_STATUS_PATH.exists():
        try:
            status = json.loads(CURRENT_GATE_STATUS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        if isinstance(status, dict):
            triage = status.get("latest_stopline_triage")
            if triage:
                return str(triage)
    triage_files = sorted(RUN_DOC_ROOT.glob("STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_*.md"))
    return str(triage_files[-1]) if triage_files else None


def build_launch_command(*, reuse_panes: str, run_id: str, session: str) -> list[str]:
    return [
        sys.executable,
        str(TMUX_LAUNCHER),
        "--repo",
        str(REPO_ROOT),
        "--starter-folder",
        str(STARTER_FOLDER),
        "--session",
        session,
        "--orchestrator-ping-mode",
        "monitor-only",
        "--agents",
        "751,752,753",
        "--reuse-panes",
        reuse_panes,
        "--no-start-sessions",
        "--parallel-groups",
        "751=agent751_752_753_validate_only_root,752=agent751_752_753_validate_only_root,753=agent751_752_753_validate_only_root",
        "--run-id",
        run_id,
        "--mode",
        "hybrid",
        "--submit-delay",
        "0.35",
    ]


def _parse_reuse_panes(raw: str) -> list[str]:
    return [pane.strip() for pane in raw.split(",") if pane.strip()]


def _validate_reuse_panes(raw: str) -> tuple[list[str], list[str]]:
    panes = _parse_reuse_panes(raw)
    current_pane = os.environ.get("TMUX_PANE", "").strip()
    if len(panes) != 3:
        return panes, ["exactly_three_reuse_panes_required"]
    if len(set(panes)) != len(panes):
        return panes, ["unique_reuse_panes_required"]
    if any(re.fullmatch(r"%\d+", pane) is None for pane in panes):
        return panes, ["pane_ids_must_be_percent_ids"]
    if current_pane and current_pane in panes:
        return panes, ["reuse_panes_include_current_tmux_pane"]
    return panes, []


def _validate_live_reuse_panes(panes: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    identities: list[dict[str, str]] = []
    for pane in panes:
        try:
            raw_identity = subprocess.check_output(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    pane,
                    "#{pane_id}\t#{pane_current_command}\t#{pane_current_path}",
                ],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            errors.append("reuse_pane_unavailable")
            identities.append({"pane": pane})
            continue
        fields = raw_identity.split("\t")
        pane_id = fields[0] if len(fields) > 0 else pane
        command = fields[1] if len(fields) > 1 else ""
        current_path = fields[2] if len(fields) > 2 else ""
        identities.append({"pane": pane_id, "command": command, "path": current_path})
        if command not in {"codex", "codex-aarch64-a"}:
            errors.append("reuse_pane_not_codex")
        if current_path != str(REPO_ROOT):
            errors.append("reuse_pane_not_in_repo")
    return identities, sorted(set(errors))


def _blocked_payload(
    *,
    stage: str,
    errors: list[str],
    readiness_payload: dict,
    review_pack: dict | None = None,
    **extra,
) -> dict:
    return {
        "ok": False,
        "stage": stage,
        "errors": errors,
        "readiness": readiness_payload,
        "db_sha256": readiness_payload.get("db_sha256"),
        "workbook_sha256": readiness_payload.get("workbook_sha256"),
        "expected_db_sha256": readiness_payload.get("expected_db_sha256"),
        "expected_workbook_sha256": readiness_payload.get("expected_workbook_sha256"),
        "db_sha256_matches_expected": readiness_payload.get("db_sha256_matches_expected"),
        "workbook_sha256_matches_expected": readiness_payload.get(
            "workbook_sha256_matches_expected"
        ),
        "latest_completion_audit": _latest_completion_audit(),
        "latest_stopline_triage": _latest_stopline_triage(),
        "latest_answer_search": _current_answer_search_info(),
        "review_pack": review_pack if review_pack is not None else _current_review_pack_info(),
        **extra,
    }


def _default_run_id() -> str:
    return "codecaptain_agent751_752_753_validate_only_wave_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fail-closed launcher for Agents751/752/753")
    p.add_argument("--reuse-panes", help="comma-separated existing Codex pane IDs, for example %326,%327,%329")
    p.add_argument("--run-id", default=_default_run_id())
    p.add_argument("--session", default="autonomous_business")
    p.add_argument("--dry-run", action="store_true", help="print the launch command without running it")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    readiness = run_readiness_check()
    readiness_payload = asdict(readiness) if hasattr(readiness, "__dataclass_fields__") else readiness.__dict__
    if not readiness.ok:
        print(
            json.dumps(
                _blocked_payload(
                    stage="readiness",
                    errors=readiness_payload.get("errors", []),
                    readiness_payload=readiness_payload,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if readiness_payload.get("decision_token") != GREEN_TOKEN:
        print(
            json.dumps(
                _blocked_payload(
                    stage="decision_token",
                    errors=["readiness_decision_token_not_exact_green"],
                    readiness_payload=readiness_payload,
                    expected_decision_token=GREEN_TOKEN,
                    actual_decision_token=readiness_payload.get("decision_token"),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    review_pack = _current_review_pack_info()
    review_pack_errors = review_pack_blocking_errors(review_pack)
    if review_pack_errors:
        print(
            json.dumps(
                _blocked_payload(
                    stage="review_pack",
                    errors=review_pack_errors,
                    readiness_payload=readiness_payload,
                    review_pack=review_pack,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    if not args.reuse_panes:
        print(
            json.dumps(
                _blocked_payload(
                    stage="reuse_panes",
                    errors=["reuse_panes_required"],
                    readiness_payload=readiness_payload,
                    reuse_pane_count=0,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    reuse_panes, reuse_pane_errors = _validate_reuse_panes(args.reuse_panes)
    if reuse_pane_errors:
        print(
            json.dumps(
                _blocked_payload(
                    stage="reuse_panes",
                    errors=reuse_pane_errors,
                    readiness_payload=readiness_payload,
                    reuse_panes=args.reuse_panes,
                    reuse_pane_count=len(reuse_panes),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    cmd = build_launch_command(reuse_panes=args.reuse_panes, run_id=args.run_id, session=args.session)
    reuse_pane_identities, live_reuse_pane_errors = _validate_live_reuse_panes(reuse_panes)
    if live_reuse_pane_errors:
        print(
            json.dumps(
                _blocked_payload(
                    stage="live_reuse_panes",
                    errors=live_reuse_pane_errors,
                    readiness_payload=readiness_payload,
                    reuse_panes=args.reuse_panes,
                    reuse_pane_identities=reuse_pane_identities,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "command": cmd,
                    "reuse_pane_identities": reuse_pane_identities,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    launch_result = subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    print(
        json.dumps(
            {
                "ok": launch_result.returncode == 0,
                "launched": launch_result.returncode == 0,
                "command": cmd,
                "reuse_pane_identities": reuse_pane_identities,
                "tmux_launcher_returncode": launch_result.returncode,
                "tmux_launcher_stdout": launch_result.stdout,
                "tmux_launcher_stderr": launch_result.stderr,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return launch_result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
