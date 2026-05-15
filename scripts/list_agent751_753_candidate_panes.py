#!/usr/bin/env python3
"""List read-only candidate Codex panes for the Agent751/752/753 guarded launch."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_agent751_753_after_agent750 import (  # noqa: E402
    GREEN_TOKEN,
    _latest_completion_audit,
    _latest_stopline_triage,
    _current_review_pack_info,
    run_readiness_check,
)
from scripts.agent750_review_pack_status import review_pack_blocking_errors  # noqa: E402
from scripts.report_agent750_next_action import current_answer_search_info  # noqa: E402

CODEX_COMMANDS = {"codex", "codex-aarch64-a"}
DEFAULT_PREFERRED_SESSION = "autonomous_business"


def parse_tmux_panes(raw: str) -> list[dict[str, str]]:
    panes: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 4)
        while len(parts) < 5:
            parts.append("")
        pane_id, command, current_path, location, title = parts
        panes.append(
            {
                "pane_id": pane_id,
                "command": command,
                "current_path": current_path,
                "location": location,
                "pane_title": title,
            }
        )
    return panes


def _location_parts(location: str) -> tuple[str, int, int]:
    session, _, pane_ref = str(location or "").partition(":")
    window_text, _, pane_text = pane_ref.partition(".")
    try:
        window_index = int(window_text)
    except ValueError:
        window_index = -1
    try:
        pane_index = int(pane_text)
    except ValueError:
        pane_index = 9999
    return session, window_index, pane_index


def _candidate_sort_key(row: dict[str, str], preferred_session: str) -> tuple[int, int, int, str]:
    session, window_index, pane_index = _location_parts(row.get("location", ""))
    preferred_rank = 0 if session == preferred_session else 1
    return (preferred_rank, -window_index, pane_index, row.get("pane_id", ""))


def summarize_candidates(
    panes: list[dict[str, str]],
    *,
    repo_path: str,
    preferred_session: str = DEFAULT_PREFERRED_SESSION,
    excluded_panes: set[str] | None = None,
) -> dict:
    candidates: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    repo = str(Path(repo_path))
    excluded = set(excluded_panes or set())
    for pane in panes:
        pane_id = pane.get("pane_id", "")
        command = pane.get("command", "")
        current_path = pane.get("current_path", "")
        row = dict(pane)
        if pane_id in excluded:
            row["reject_reason"] = "excluded_pane"
            rejected.append(row)
            continue
        if command not in CODEX_COMMANDS:
            row["reject_reason"] = "not_codex"
            rejected.append(row)
            continue
        if current_path != repo:
            row["reject_reason"] = "wrong_path"
            rejected.append(row)
            continue
        candidates.append(row)

    candidates = sorted(candidates, key=lambda row: _candidate_sort_key(row, preferred_session))
    suggested = ",".join(row["pane_id"] for row in candidates[:3])
    ready = len(candidates) >= 3
    return {
        "ok": True,
        "repo_path": repo,
        "preferred_session": preferred_session,
        "excluded_panes": sorted(excluded),
        "candidate_count": len(candidates),
        "ready_for_launch_selection": ready,
        "candidate_panes": candidates,
        "rejected_panes": rejected,
        "suggested_reuse_panes": suggested if ready else "",
        "guarded_launch_command": (
            f"python3 scripts/launch_agent751_753_after_agent750.py --reuse-panes {suggested}"
            if ready
            else ""
        ),
        "note": "Read-only pane discovery only. This does not launch agents or ping tmux panes.",
    }


def list_tmux_panes() -> str:
    return subprocess.check_output(
        [
            "tmux",
            "list-panes",
            "-a",
            "-F",
            "#{pane_id}\t#{pane_current_command}\t#{pane_current_path}\t#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}",
        ],
        text=True,
        stderr=subprocess.STDOUT,
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only candidate pane lister for Agent751/752/753")
    p.add_argument("--repo", type=Path, default=REPO_ROOT)
    p.add_argument("--preferred-session", default=DEFAULT_PREFERRED_SESSION)
    p.add_argument(
        "--exclude-panes",
        default="",
        help="Optional comma-separated %%pane ids to exclude from execution-agent reuse.",
    )
    p.add_argument(
        "--include-current-pane",
        action="store_true",
        help="Do not automatically exclude TMUX_PANE. Use only for tests or non-interactive shells.",
    )
    p.add_argument("--json-only", action="store_true")
    return p


def _parse_excluded_panes(raw: str) -> set[str]:
    return {item.strip() for item in str(raw or "").split(",") if item.strip()}


def _readiness_payload(readiness) -> dict:
    return asdict(readiness) if hasattr(readiness, "__dataclass_fields__") else readiness.__dict__


def _blocked_payload(
    *,
    status: str,
    errors: list[str],
    readiness_payload: dict,
    repo_path: Path,
    preferred_session: str,
    excluded_panes: set[str],
    note: str,
    detail: str | None = None,
    actual_decision_token: str | None = None,
) -> dict:
    payload = {
        "ok": False,
        "status": status,
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
        "latest_answer_search": current_answer_search_info(),
        "review_pack": _current_review_pack_info(),
        "repo_path": str(repo_path.expanduser().resolve()),
        "preferred_session": preferred_session,
        "excluded_panes": sorted(excluded_panes),
        "candidate_count": 0,
        "ready_for_launch_selection": False,
        "candidate_panes": [],
        "rejected_panes": [],
        "suggested_reuse_panes": "",
        "guarded_launch_command": "",
        "note": note,
    }
    if detail is not None:
        payload["detail"] = detail
    if actual_decision_token is not None:
        payload["expected_decision_token"] = GREEN_TOKEN
        payload["actual_decision_token"] = actual_decision_token
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    excluded_panes = _parse_excluded_panes(args.exclude_panes)
    current_pane = os.environ.get("TMUX_PANE", "").strip()
    if current_pane and not args.include_current_pane:
        excluded_panes.add(current_pane)

    readiness = run_readiness_check()
    readiness_payload = _readiness_payload(readiness)
    if not readiness.ok:
        payload = _blocked_payload(
            status="BLOCKED_BY_READINESS",
            errors=readiness_payload.get("errors", []),
            readiness_payload=readiness_payload,
            repo_path=args.repo,
            preferred_session=args.preferred_session,
            excluded_panes=excluded_panes,
            note="Pane discovery is readiness-gated; tmux panes were not listed.",
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    if readiness_payload.get("decision_token") != GREEN_TOKEN:
        payload = _blocked_payload(
            status="BLOCKED_BY_DECISION_TOKEN",
            errors=["readiness_decision_token_not_exact_green"],
            readiness_payload=readiness_payload,
            repo_path=args.repo,
            preferred_session=args.preferred_session,
            excluded_panes=excluded_panes,
            note="Pane discovery requires the exact Agent750 GREEN token; tmux panes were not listed.",
            actual_decision_token=readiness_payload.get("decision_token"),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    review_pack = _current_review_pack_info()
    review_pack_errors = review_pack_blocking_errors(review_pack)
    if review_pack_errors:
        payload = _blocked_payload(
            status="BLOCKED_BY_REVIEW_PACK",
            errors=review_pack_errors,
            readiness_payload=readiness_payload,
            repo_path=args.repo,
            preferred_session=args.preferred_session,
            excluded_panes=excluded_panes,
            note="Pane discovery requires a healthy Agent750 review pack; tmux panes were not listed.",
        )
        payload["review_pack"] = review_pack
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    try:
        raw = list_tmux_panes()
        payload = summarize_candidates(
            parse_tmux_panes(raw),
            repo_path=str(args.repo.expanduser().resolve()),
            preferred_session=args.preferred_session,
            excluded_panes=excluded_panes,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        payload = _blocked_payload(
            status="TMUX_LIST_PANES_FAILED",
            errors=["tmux_list_panes_failed"],
            readiness_payload=readiness_payload,
            repo_path=args.repo,
            preferred_session=args.preferred_session,
            excluded_panes=excluded_panes,
            note="Pane discovery could not list tmux panes; no launch command was suggested.",
            detail=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    if not payload["ready_for_launch_selection"]:
        payload["ok"] = False
        payload["status"] = "INSUFFICIENT_CANDIDATE_PANES"
        payload["errors"] = ["fewer_than_three_candidate_panes"]
        payload["readiness"] = readiness_payload
        payload["review_pack"] = _current_review_pack_info()
        payload["note"] = (
            "Pane discovery is read-only and found fewer than three reusable Codex panes; "
            "no launch command was suggested."
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ready_for_launch_selection"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
