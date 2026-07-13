from __future__ import annotations

import gzip
import json
import plistlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.rotate_daily_shipping_logs import (
    APPLY_ENV,
    discover_log_paths,
    rotate_daily_shipping_logs,
)


UTC = timezone.utc
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _manifest(tmp_path: Path, project: Path, *, max_bytes: int = 16) -> Path:
    payload = {
        "project_root": str(project),
        "schedulers": [
            {
                "stdout": "${PROJECT_ROOT}/runtime_logs/watch_stdout.log",
                "stderr": "${PROJECT_ROOT}/runtime_logs/watch_stderr.log",
            },
            {
                "stdout": "${PROJECT_ROOT}/runtime_logs/watch_stdout.log",
                "stderr": "${PROJECT_ROOT}/runtime_logs/import_stderr.log",
            },
        ],
        "observability": {
            "log_maintenance": {
                "max_bytes": max_bytes,
                "keep_archives_per_log": 14,
                "archive_root": str(tmp_path / "archives"),
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_discovery_is_manifest_derived_deduplicated_and_runtime_scoped(
    tmp_path: Path,
) -> None:
    project = tmp_path / "repo"
    manifest = _manifest(tmp_path, project)

    paths = discover_log_paths(manifest_path=manifest, project_root=project)

    assert [path.name for path in paths] == [
        "import_stderr.log",
        "watch_stderr.log",
        "watch_stdout.log",
    ]
    assert all(path.parent == project / "runtime_logs" for path in paths)


def test_dry_run_reports_oversize_without_writing(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    logs = project / "runtime_logs"
    logs.mkdir(parents=True)
    source = logs / "watch_stdout.log"
    source.write_text("x" * 32, encoding="utf-8")
    manifest = _manifest(tmp_path, project)

    report = rotate_daily_shipping_logs(
        manifest_path=manifest,
        project_root=project,
        apply=False,
    )

    assert report["gate"] == "DRY_RUN"
    assert report["oversize_count"] == 1
    assert source.read_text(encoding="utf-8") == "x" * 32
    assert not (tmp_path / "archives").exists()


def test_apply_requires_explicit_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "repo"
    manifest = _manifest(tmp_path, project)
    monkeypatch.delenv(APPLY_ENV, raising=False)

    with pytest.raises(PermissionError, match=APPLY_ENV):
        rotate_daily_shipping_logs(
            manifest_path=manifest,
            project_root=project,
            apply=True,
        )


def test_apply_atomically_reopens_log_and_verifies_gzip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "repo"
    logs = project / "runtime_logs"
    logs.mkdir(parents=True)
    source = logs / "watch_stdout.log"
    original = b"one complete launchd log\n"
    source.write_bytes(original)
    manifest = _manifest(tmp_path, project)
    monkeypatch.setenv(APPLY_ENV, "1")

    report = rotate_daily_shipping_logs(
        manifest_path=manifest,
        project_root=project,
        apply=True,
        now=datetime(2026, 7, 13, 18, 0, tzinfo=UTC),
        no_open_handles=lambda _path: True,
    )

    item = report["items"][0]
    archive = Path(item["archive"])
    assert report["gate"] == "GREEN"
    assert report["rotated_count"] == 1
    assert source.is_file() and source.stat().st_size == 0
    assert gzip.decompress(archive.read_bytes()) == original
    assert Path(item["manifest"]).is_file()
    assert oct((tmp_path / "archives").stat().st_mode & 0o777) == "0o700"


def test_candidate_log_maintenance_launchagent_is_inert() -> None:
    plist = PROJECT_ROOT / "config" / "com.example.daily-shipping-log-maintenance.plist"
    payload = plistlib.loads(plist.read_bytes())

    assert payload["Label"] == "com.example.daily-shipping-log-maintenance"
    assert payload["RunAtLoad"] is False
    assert payload["KeepAlive"] is False
    assert payload["EnvironmentVariables"][APPLY_ENV] == "1"
    assert not (Path.home() / "Library" / "LaunchAgents" / plist.name).exists()
