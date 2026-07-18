#!/usr/bin/env python3
"""Produce a weekly, read-only Git hygiene report for one repository."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "git_hygiene"


class GitHygieneError(RuntimeError):
    pass


@dataclass(frozen=True)
class HygieneThresholds:
    max_unpushed_commits: int = 0
    max_dirty_entries: int = 0
    max_worktrees: int = 1
    max_stashes: int = 0
    max_staged_age_seconds: int = 86400


def _run_git(
    repo: Path,
    args: Sequence[str],
    *,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode(errors="replace").strip()
        raise GitHygieneError(f"git {' '.join(args)} failed: {stderr}")
    return result


def _count_porcelain_v1_z(payload: bytes) -> int:
    """Count entries while treating rename/copy source records as metadata."""
    parts = payload.split(b"\0")
    count = 0
    index = 0
    while index < len(parts):
        record = parts[index]
        if not record:
            index += 1
            continue
        status = record[:2].decode("ascii", errors="replace")
        count += 1
        index += 2 if "R" in status or "C" in status else 1
    return count


def _git_path(repo: Path, name: str) -> Path:
    raw = _run_git(repo, ["rev-parse", "--git-path", name]).stdout.strip()
    path = Path(raw)
    return path if path.is_absolute() else repo / path


def collect_git_hygiene(
    repo: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise GitHygieneError(f"repository path is not a directory: {repo}")
    if _run_git(repo, ["rev-parse", "--is-inside-work-tree"], check=False).returncode != 0:
        raise GitHygieneError(f"not a Git worktree: {repo}")

    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc)

    branch = _run_git(repo, ["branch", "--show-current"]).stdout.strip()
    head_result = _run_git(repo, ["rev-parse", "HEAD"], check=False)
    head = head_result.stdout.strip() if head_result.returncode == 0 else ""

    upstream_result = _run_git(
        repo,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else ""
    if not head:
        unpushed_commits = 0
    elif upstream:
        unpushed_commits = int(
            _run_git(repo, ["rev-list", "--count", f"{upstream}..HEAD"]).stdout.strip()
        )
    else:
        unpushed_commits = int(_run_git(repo, ["rev-list", "--count", "HEAD"]).stdout.strip())

    staged_payload = _run_git(
        repo,
        ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
        text=False,
    ).stdout
    staged_files = len([item for item in staged_payload.split(b"\0") if item])

    staged_age_seconds = 0
    staged_since = ""
    if staged_files:
        index_path = _git_path(repo, "index")
        if index_path.exists():
            index_mtime = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc)
            staged_age_seconds = max(0, int((observed_at - index_mtime).total_seconds()))
            staged_since = index_mtime.isoformat()

    status_payload = _run_git(
        repo,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        text=False,
    ).stdout
    dirty_entries = _count_porcelain_v1_z(status_payload)

    worktree_output = _run_git(repo, ["worktree", "list", "--porcelain"]).stdout
    worktrees = sum(1 for line in worktree_output.splitlines() if line.startswith("worktree "))

    stash_result = _run_git(
        repo,
        ["rev-list", "--walk-reflogs", "--count", "refs/stash"],
        check=False,
    )
    stashes = int(stash_result.stdout.strip()) if stash_result.returncode == 0 else 0

    return {
        "repo": str(repo),
        "observed_at": observed_at.isoformat(),
        "branch": branch,
        "head": head,
        "upstream": upstream,
        "upstream_missing": not bool(upstream),
        "unpushed_commits": unpushed_commits,
        "dirty_entries": dirty_entries,
        "worktrees": worktrees,
        "stashes": stashes,
        "staged_files": staged_files,
        "staged_age_seconds": staged_age_seconds,
        "staged_since": staged_since,
    }


def threshold_findings(
    counts: dict[str, Any],
    thresholds: HygieneThresholds,
) -> list[dict[str, Any]]:
    checks = (
        ("unpushed_commits", thresholds.max_unpushed_commits),
        ("dirty_entries", thresholds.max_dirty_entries),
        ("worktrees", thresholds.max_worktrees),
        ("stashes", thresholds.max_stashes),
        ("staged_age_seconds", thresholds.max_staged_age_seconds),
    )
    findings: list[dict[str, Any]] = []
    for metric, maximum in checks:
        actual = int(counts.get(metric) or 0)
        if actual > maximum:
            findings.append(
                {
                    "code": f"{metric.upper()}_ABOVE_THRESHOLD",
                    "metric": metric,
                    "actual": actual,
                    "maximum": maximum,
                }
            )
    if counts.get("upstream_missing"):
        findings.append(
            {
                "code": "UPSTREAM_MISSING",
                "metric": "upstream_missing",
                "actual": True,
                "maximum": False,
            }
        )
    return findings


def write_report(output_root: Path, report: dict[str, Any]) -> Path:
    target_root = Path(output_root)
    target_root.mkdir(parents=True, exist_ok=True)
    stamp = str(report["observed_at"]).replace("-", "").replace(":", "").split(".")[0]
    target = target_root / f"git_hygiene_{stamp.replace('+0000', 'Z')}.json"
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _enqueue_warning(report: dict[str, Any], report_path: Path) -> bool:
    if not report["findings"]:
        return False
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from core.alerts.ops_alert_outbox import enqueue_alert

    return enqueue_alert(
        title="Weekly Git hygiene warning",
        lines=[
            f"Repository: {report['counts']['repo']}",
            "Findings: " + ", ".join(item["code"] for item in report["findings"]),
            f"Report: {report_path}",
            "Local-only warning; no external delivery is attempted.",
        ],
        severity="WARN",
        dedup_key=f"git_hygiene:{report['counts']['repo']}:{report['observed_at'][:10]}",
        local_only=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-unpushed-commits", type=int, default=0)
    parser.add_argument("--max-dirty-entries", type=int, default=0)
    parser.add_argument("--max-worktrees", type=int, default=1)
    parser.add_argument("--max-stashes", type=int, default=0)
    parser.add_argument("--max-staged-age-seconds", type=int, default=86400)
    parser.add_argument("--no-alert", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    thresholds = HygieneThresholds(
        max_unpushed_commits=args.max_unpushed_commits,
        max_dirty_entries=args.max_dirty_entries,
        max_worktrees=args.max_worktrees,
        max_stashes=args.max_stashes,
        max_staged_age_seconds=args.max_staged_age_seconds,
    )
    counts = collect_git_hygiene(args.repo)
    findings = threshold_findings(counts, thresholds)
    report = {
        "schema_version": 1,
        "status": "WARN" if findings else "PASS",
        "observed_at": counts["observed_at"],
        "counts": counts,
        "thresholds": asdict(thresholds),
        "findings": findings,
        "alert": {"required": bool(findings), "enqueued": False, "local_only": True},
    }
    report_path = write_report(args.output_root, report)
    if findings and not args.no_alert:
        report["alert"]["enqueued"] = bool(_enqueue_warning(report, report_path))
        write_report(args.output_root, report)
    report["report_path"] = str(report_path.resolve())
    write_report(args.output_root, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{report['status']}: {report_path}")
        for finding in findings:
            print(
                f"WARN: {finding['metric']}={finding['actual']} "
                f"> {finding['maximum']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
