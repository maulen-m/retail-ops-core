from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.archive_cold_evidence import (
    APPLY_ENV,
    archive_cold_tree,
    archive_evidence,
    inspect_cold_tree,
    inspect_evidence,
    verify_archive,
)


UTC = timezone.utc


def _run_fixture(tmp_path: Path, *, age_days: int = 30) -> tuple[Path, Path]:
    project = tmp_path / "repo"
    run = project / ".claude" / "orchestrator_runs" / "20260101_120000_closed_run"
    evidence = run / "evidence"
    evidence.mkdir(parents=True)
    (run / "final_handoff.md").write_text("Gate: GREEN\n", encoding="utf-8")
    (evidence / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
    nested = evidence / "snapshot"
    nested.mkdir()
    (nested / "app.db").write_bytes(b"sqlite-like-test-bytes" * 100)
    stamp = (datetime.now(UTC) - timedelta(days=age_days)).timestamp()
    for path in (evidence / "report.json", nested / "app.db", nested, evidence, run):
        os.utime(path, (stamp, stamp))
    return project, run


def test_inspection_reports_restorable_tree_without_mutating(tmp_path: Path) -> None:
    project, run = _run_fixture(tmp_path)

    report = inspect_evidence(run=run, project_root=project, min_age_days=14)

    assert report["gate"] == "DRY_RUN"
    assert report["file_count"] == 2
    assert report["logical_bytes"] > 0
    assert (run / "evidence").is_dir()
    assert not (run / "evidence.tar.zst").exists()


def test_out_of_scope_run_is_refused(tmp_path: Path) -> None:
    project, _ = _run_fixture(tmp_path)
    outside = tmp_path / "other" / "run"
    (outside / "evidence").mkdir(parents=True)

    with pytest.raises(ValueError, match="orchestrator_runs"):
        inspect_evidence(run=outside, project_root=project, min_age_days=14)


def test_fresh_run_is_refused(tmp_path: Path) -> None:
    project, run = _run_fixture(tmp_path, age_days=1)

    with pytest.raises(ValueError, match="not cold enough"):
        inspect_evidence(run=run, project_root=project, min_age_days=14)


def test_apply_requires_explicit_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, run = _run_fixture(tmp_path)
    monkeypatch.delenv(APPLY_ENV, raising=False)

    with pytest.raises(PermissionError, match=APPLY_ENV):
        archive_evidence(run=run, project_root=project, min_age_days=14, apply=True)


@pytest.mark.skipif(
    not Path("/opt/homebrew/bin/zstd").exists(), reason="zstd unavailable"
)
def test_apply_creates_verified_archive_before_retiring_expanded_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, run = _run_fixture(tmp_path)
    monkeypatch.setenv(APPLY_ENV, "1")

    report = archive_evidence(
        run=run,
        project_root=project,
        min_age_days=14,
        apply=True,
    )

    archive = run / "evidence.tar.zst"
    manifest = json.loads(
        (run / "evidence.archive_manifest.json").read_text(encoding="utf-8")
    )
    verified = verify_archive(archive, expected_file_count=2)
    assert report["gate"] == "GREEN"
    assert report["expanded_tree_retired"] is True
    assert not (run / "evidence").exists()
    assert archive.is_file()
    assert manifest["archive_sha256"] == report["archive_sha256"]
    assert verified["gate"] == "GREEN"
    assert verified["file_count"] == 2


@pytest.mark.skipif(
    not Path("/opt/homebrew/bin/zstd").exists(), reason="zstd unavailable"
)
def test_cold_validation_packet_uses_same_verified_archive_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "repo"
    target = project / "exports" / "validation" / "closed_packet_20260101"
    target.mkdir(parents=True)
    (target / "copy.db").write_bytes(b"repeated-db-proof" * 100)
    stamp = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    os.utime(target / "copy.db", (stamp, stamp))
    os.utime(target, (stamp, stamp))
    monkeypatch.setenv(APPLY_ENV, "1")

    dry_run = inspect_cold_tree(target=target, project_root=project, min_age_days=14)
    report = archive_cold_tree(
        target=target,
        project_root=project,
        min_age_days=14,
        apply=True,
    )

    assert dry_run["scope"] == "validation_packet"
    assert report["gate"] == "GREEN"
    assert report["expanded_tree_retired"] is True
    assert not target.exists()
    assert target.with_name(f"{target.name}.tar.zst").is_file()
    assert target.with_name(f"{target.name}.archive_manifest.json").is_file()
