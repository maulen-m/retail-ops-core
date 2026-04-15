#!/usr/bin/env python3
"""Scaffold a standard parallel rollout pack for the Autonomous_business repo."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from textwrap import dedent


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    if not normalized:
        raise ValueError("slug cannot be empty after normalization")
    return normalized


def ensure_repo_root(repo_root: Path) -> None:
    required = [
        repo_root / "AGENTS.md",
        repo_root / "docs" / "00_START_HERE.md",
        repo_root / "scripts",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"repo root check failed, missing required paths: {missing}")


def write_text(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite existing file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_plan(
    repo_root: Path,
    run_dir: Path,
    handoff_dir: Path,
    purpose: str,
    as_of: str,
    focus_b: str,
    focus_c: str,
) -> str:
    repo_name = repo_root.name
    return dedent(
        f"""\
        PLAN

        Purpose

        {purpose}

        Repo

        - `{repo_root}`

        Canonical protocol

        - `docs/PARALLEL_EXECUTION_PROTOCOL.md`

        Read first

        - `AGENTS.md`
        - `docs/00_START_HERE.md`
        - `docs/PARALLEL_EXECUTION_PROTOCOL.md`

        Execution posture

        - one write-capable execution agent
        - two read-only analyst agents
        - fail-closed
        - no hidden provenance

        Shared handoff folder

        - `{handoff_dir}`

        As-of window

        - `{as_of or "not specified"}`

        Role split

        Agent A

        - execution agent
        - only writer in the repo
        - only agent allowed to mutate `db/app.db`
        - reads analyst reports and executes the repair path

        Agent B

        - read-only analyst
        - focus: {focus_b}

        Agent C

        - read-only analyst
        - focus: {focus_c}

        First-pass independence rule

        - Agent B publishes before reading Agent C
        - Agent C publishes before reading Agent B
        - Agent A consumes both reports
        - second-pass cross-review happens only if Agent A explicitly requests it

        Required handoff files

        - `README.md`
        - `status_board.md`
        - `agent_b_report.md`
        - `agent_c_report.md`
        - `agent_a_execution_log.md`

        Launch order

        1. Agent B
        2. Agent C
        3. Agent A after B and C publish first-pass reports

        Stop rules

        - analysts do not modify repo state
        - execution agent does not start DB mutation before upstream analysis unless running intentionally in single-agent mode
        - no source swap without explicit provenance

        Generated from

        - `python3 scripts/init_parallel_rollout.py`
        - repo `{repo_name}`
        - run dir `{run_dir}`
        """
    )


def build_prompt_agent_a(repo_root: Path, plan_rel: str, handoff_dir: Path) -> str:
    return dedent(
        f"""\
        PROMPT_AGENT_A

        Read first

        - `AGENTS.md`
        - `docs/00_START_HERE.md`
        - `{plan_rel}`
        - `docs/PARALLEL_EXECUTION_PROTOCOL.md`

        Shared handoff folder

        - `{handoff_dir}`

        Your role

        - only write-capable execution agent
        - only agent allowed to write shared repo state
        - only agent allowed to mutate `db/app.db`

        Your job

        - read the analyst reports
        - execute the plan in causal order
        - log actions and results to `agent_a_execution_log.md`

        Rules

        - do not loosen validators
        - do not hide provenance
        - do not start DB writes before upstream analysis unless single-agent mode was explicitly chosen

        Success

        - task is completed or narrowed honestly to a smaller explicit stopline
        """
    )


def build_prompt_agent_b(repo_root: Path, plan_rel: str, handoff_dir: Path, focus_b: str) -> str:
    return dedent(
        f"""\
        PROMPT_AGENT_B

        Read first

        - `AGENTS.md`
        - `docs/00_START_HERE.md`
        - `{plan_rel}`
        - `docs/PARALLEL_EXECUTION_PROTOCOL.md`

        Shared handoff folder

        - `{handoff_dir}`

        Your role

        - read-only analyst
        - focus: {focus_b}

        Rules

        - do not modify repo files
        - do not mutate the DB
        - do not read Agent C's report before publishing your own first-pass findings

        Output

        - write findings to `agent_b_report.md`
        - keep findings concise, source-backed, and actionable for Agent A
        """
    )


def build_prompt_agent_c(repo_root: Path, plan_rel: str, handoff_dir: Path, focus_c: str) -> str:
    return dedent(
        f"""\
        PROMPT_AGENT_C

        Read first

        - `AGENTS.md`
        - `docs/00_START_HERE.md`
        - `{plan_rel}`
        - `docs/PARALLEL_EXECUTION_PROTOCOL.md`

        Shared handoff folder

        - `{handoff_dir}`

        Your role

        - read-only analyst
        - focus: {focus_c}

        Rules

        - do not modify repo files
        - do not mutate the DB
        - do not read Agent B's report before publishing your own first-pass findings

        Output

        - write findings to `agent_c_report.md`
        - keep findings concise, source-backed, and actionable for Agent A
        """
    )


def build_launch_order(run_dir: Path) -> str:
    return dedent(
        f"""\
        LAUNCH_ORDER

        Launch sequence

        1. Agent B:
           Read `PROMPT_AGENT_B.md` in this folder and start.
        2. Agent C:
           Read `PROMPT_AGENT_C.md` in this folder and start.
        3. Agent A:
           After B and C publish first-pass findings, read `PROMPT_AGENT_A.md` in this folder and start.

        This run pack lives in:

        - `{run_dir}`
        """
    )


def build_handoff_readme(repo_root: Path, run_dir: Path) -> str:
    return dedent(
        f"""\
        Shared handoff folder for a parallel rollout in `{repo_root.name}`.

        Canonical run pack:

        - `{run_dir}`

        Required files

        - `status_board.md`
        - `agent_b_report.md`
        - `agent_c_report.md`
        - `agent_a_execution_log.md`

        Rules

        - B and C publish first-pass findings independently
        - A reads both and executes
        - repo truth changes happen only through Agent A
        """
    )


def build_status_board() -> str:
    return dedent(
        """\
        # Status Board

        Current stage

        - waiting to launch agents

        Published reports

        - Agent B: pending
        - Agent C: pending
        - Agent A: pending

        Execution unlocked for Agent A

        - no
        """
    )


def build_report_stub(title: str) -> str:
    return dedent(
        f"""\
        # {title}

        Scope worked

        - pending

        Sources inspected

        - pending

        Commands run

        - pending

        Findings

        - pending

        Exact next action for Agent A

        - pending

        Uncertainties / open risks

        - pending
        """
    )


def build_execution_log_stub() -> str:
    return dedent(
        """\
        # Agent A Execution Log

        Ordered actions taken

        - pending

        Commands run

        - pending

        Before / after gate results

        - pending

        DB backup path

        - pending

        Rollback steps

        - pending
        """
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Run slug, e.g. march19-green-repair")
    parser.add_argument("--purpose", required=True, help="One-sentence purpose for the run")
    parser.add_argument("--as-of", default="", help="Optional as-of date, e.g. 2026-03-19")
    parser.add_argument("--date", default=str(date.today()), help="Run date for folder naming")
    parser.add_argument("--repo-root", default=".", help="Repo root to scaffold into")
    parser.add_argument(
        "--focus-b",
        default="proof artifact + source provenance + OPEX analysis",
        help="Read-only focus for Agent B",
    )
    parser.add_argument(
        "--focus-c",
        default="DB divergence + chronology + validator-surface analysis",
        help="Read-only focus for Agent C",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files")
    parser.add_argument("--dry-run", action="store_true", help="Print planned paths without writing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    slug = slugify(args.slug)
    repo_root = Path(args.repo_root).resolve()
    ensure_repo_root(repo_root)

    repo_name = repo_root.name
    run_dir = repo_root / "docs" / "parallel_runs" / f"{args.date}_{slug}"
    handoff_dir = Path.home() / "Docs" / f"{repo_name}_agent_handoffs" / f"{args.date}_{slug}"

    plan_path = run_dir / "PLAN.md"
    prompt_a_path = run_dir / "PROMPT_AGENT_A.md"
    prompt_b_path = run_dir / "PROMPT_AGENT_B.md"
    prompt_c_path = run_dir / "PROMPT_AGENT_C.md"
    launch_path = run_dir / "LAUNCH_ORDER.md"

    handoff_readme = handoff_dir / "README.md"
    status_board = handoff_dir / "status_board.md"
    report_b = handoff_dir / "agent_b_report.md"
    report_c = handoff_dir / "agent_c_report.md"
    exec_log = handoff_dir / "agent_a_execution_log.md"

    if args.dry_run:
        for path in [
            plan_path,
            prompt_a_path,
            prompt_b_path,
            prompt_c_path,
            launch_path,
            handoff_readme,
            status_board,
            report_b,
            report_c,
            exec_log,
        ]:
            print(path)
        return

    plan_rel = plan_path.relative_to(repo_root).as_posix()

    write_text(
        plan_path,
        build_plan(repo_root, run_dir, handoff_dir, args.purpose, args.as_of, args.focus_b, args.focus_c),
        args.force,
    )
    write_text(prompt_a_path, build_prompt_agent_a(repo_root, plan_rel, handoff_dir), args.force)
    write_text(prompt_b_path, build_prompt_agent_b(repo_root, plan_rel, handoff_dir, args.focus_b), args.force)
    write_text(prompt_c_path, build_prompt_agent_c(repo_root, plan_rel, handoff_dir, args.focus_c), args.force)
    write_text(launch_path, build_launch_order(run_dir), args.force)

    write_text(handoff_readme, build_handoff_readme(repo_root, run_dir), args.force)
    write_text(status_board, build_status_board(), args.force)
    write_text(report_b, build_report_stub("Agent B Report"), args.force)
    write_text(report_c, build_report_stub("Agent C Report"), args.force)
    write_text(exec_log, build_execution_log_stub(), args.force)

    print("Created parallel rollout pack:")
    for path in [
        plan_path,
        prompt_a_path,
        prompt_b_path,
        prompt_c_path,
        launch_path,
        handoff_readme,
        status_board,
        report_b,
        report_c,
        exec_log,
    ]:
        print(f"- {path}")


if __name__ == "__main__":
    main()
