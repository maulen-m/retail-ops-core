from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.report_git_hygiene import (
    HygieneThresholds,
    collect_git_hygiene,
    threshold_findings,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _init_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "G67 Test")
    _git(path, "config", "user.email", "g67@example.invalid")
    _write(path / "tracked.txt", "initial\n")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-m", "test: initial commit")


def test_collect_git_hygiene_counts_temp_repo_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    linked = tmp_path / "linked"
    _init_repo(repo)
    _git(tmp_path, "init", "--bare", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    _write(repo / "second.txt", "second\n")
    _git(repo, "add", "second.txt")
    _git(repo, "commit", "-m", "test: add second file")
    _git(repo, "worktree", "add", "-b", "lane/counts", str(linked), "HEAD")

    _write(repo / "tracked.txt", "stash me\n")
    _git(repo, "stash", "push", "-m", "counting stash")
    _write(repo / "untracked.txt", "dirty\n")
    _write(repo / "staged.txt", "staged\n")
    _git(repo, "add", "staged.txt")

    index_path = Path(_git(repo, "rev-parse", "--git-path", "index").stdout.strip())
    if not index_path.is_absolute():
        index_path = repo / index_path
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(index_path, (old.timestamp(), old.timestamp()))

    counts = collect_git_hygiene(repo, now=datetime.now(timezone.utc))

    assert counts["upstream"] == "origin/main"
    assert counts["unpushed_commits"] == 1
    assert counts["dirty_entries"] == 2
    assert counts["worktrees"] == 2
    assert counts["stashes"] == 1
    assert counts["staged_files"] == 1
    assert counts["staged_age_seconds"] >= 7100


def test_collect_git_hygiene_counts_all_commits_without_upstream(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    counts = collect_git_hygiene(repo)

    assert counts["upstream_missing"] is True
    assert counts["unpushed_commits"] == 1


def test_threshold_findings_are_deterministic() -> None:
    counts = {
        "unpushed_commits": 2,
        "dirty_entries": 3,
        "worktrees": 2,
        "stashes": 1,
        "staged_age_seconds": 90000,
        "upstream_missing": False,
    }

    findings = threshold_findings(counts, HygieneThresholds())

    assert [item["metric"] for item in findings] == [
        "unpushed_commits",
        "dirty_entries",
        "worktrees",
        "stashes",
        "staged_age_seconds",
    ]
