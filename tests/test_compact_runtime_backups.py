from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from scripts.compact_runtime_backups import (
    APPLY_ENV,
    RESTORE_ENV,
    CompactionLock,
    compact_backups,
    discover_candidates,
    restore_backup,
)


ZSTD = shutil.which("zstd")


def _write_old_backup(root: Path, name: str, payload: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    old = time.time() - (45 * 24 * 60 * 60)
    os.utime(path, (old, old))
    return path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_discovery_is_oldest_first_and_excludes_fresh_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    oldest = _write_old_backup(root, "a.sqlite", b"oldest")
    newer = _write_old_backup(root, "nested/b.db", b"newer")
    os.utime(oldest, (oldest.stat().st_mtime - 100, oldest.stat().st_mtime - 100))
    fresh = root / "fresh.sqlite"
    fresh.write_bytes(b"fresh")
    (root / "link.sqlite").symlink_to(newer)

    candidates = discover_candidates(root, older_than_days=30, now=time.time())

    assert candidates == [oldest, newer]
    assert fresh not in candidates


def test_dry_run_never_changes_source(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    source = _write_old_backup(root, "app.sqlite", b"sqlite payload" * 100)

    report = compact_backups(root=root, older_than_days=30, apply=False, zstd_bin=ZSTD or "zstd")

    assert report["gate"] == "DRY_RUN"
    assert report["candidate_count"] == 1
    assert report["compacted_count"] == 0
    assert source.exists()
    assert not Path(f"{source}.zst").exists()


def test_apply_requires_explicit_environment_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "backups"
    _write_old_backup(root, "app.sqlite", b"payload")
    monkeypatch.delenv(APPLY_ENV, raising=False)

    with pytest.raises(PermissionError, match=APPLY_ENV):
        compact_backups(root=root, older_than_days=30, apply=True, zstd_bin=ZSTD or "zstd")


@pytest.mark.skipif(ZSTD is None, reason="zstd is required")
def test_apply_replaces_source_only_after_exact_stream_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "backups"
    payload = (b"SQLite format 3\x00" + b"repetitive-data" * 10000)
    source = _write_old_backup(root, "cycle/app.sqlite", payload)
    original_mtime = source.stat().st_mtime
    monkeypatch.setenv(APPLY_ENV, "1")

    report = compact_backups(
        root=root,
        older_than_days=30,
        apply=True,
        max_files=1,
        zstd_bin=ZSTD,
    )

    archive = Path(f"{source}.zst")
    sidecar = Path(f"{archive}.manifest.json")
    restored = subprocess.run([ZSTD, "-q", "-dc", str(archive)], check=True, capture_output=True).stdout
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    ledger_rows = [json.loads(line) for line in (root / "compaction_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

    assert report["gate"] == "GREEN"
    assert report["compacted_count"] == 1
    assert not source.exists()
    assert restored == payload
    assert archive.stat().st_mtime == pytest.approx(original_mtime, abs=1)
    assert sidecar_payload["original_sha256"] == _sha256(payload)
    assert sidecar_payload["verification"] == "zstd_test_and_decompressed_sha256_match"
    assert ledger_rows[-1]["original_relative_path"] == "cycle/app.sqlite"


@pytest.mark.skipif(ZSTD is None, reason="zstd is required")
def test_existing_archive_never_causes_source_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "backups"
    source = _write_old_backup(root, "app.sqlite", b"source")
    Path(f"{source}.zst").write_bytes(b"not-an-archive")
    monkeypatch.setenv(APPLY_ENV, "1")

    report = compact_backups(root=root, older_than_days=30, apply=True, zstd_bin=ZSTD)

    assert report["gate"] == "YELLOW"
    assert report["compacted_count"] == 0
    assert source.read_bytes() == b"source"
    assert report["items"][0]["status"] == "SKIPPED_DESTINATION_EXISTS"


def test_nonblocking_lock_refuses_concurrent_compaction(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    lock_path = root / ".backup_compaction.lock"
    with lock_path.open("a+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            with CompactionLock(lock_path):
                pass


@pytest.mark.skipif(ZSTD is None, reason="zstd is required")
def test_restore_is_gated_and_sha_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "backups"
    payload = b"restore-me" * 1000
    source = _write_old_backup(root, "app.sqlite", payload)
    monkeypatch.setenv(APPLY_ENV, "1")
    compact_backups(root=root, older_than_days=30, apply=True, zstd_bin=ZSTD)
    archive = Path(f"{source}.zst")
    output = tmp_path / "restored.sqlite"

    monkeypatch.delenv(RESTORE_ENV, raising=False)
    with pytest.raises(PermissionError, match=RESTORE_ENV):
        restore_backup(archive=archive, output=output, apply=True, zstd_bin=ZSTD)

    monkeypatch.setenv(RESTORE_ENV, "1")
    report = restore_backup(archive=archive, output=output, apply=True, zstd_bin=ZSTD)

    assert report["gate"] == "GREEN"
    assert output.read_bytes() == payload
    assert report["restored_sha256"] == _sha256(payload)
