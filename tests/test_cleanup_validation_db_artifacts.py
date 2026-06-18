from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/cleanup_validation_db_artifacts.py")


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "size_bytes", "size_mib", "class", "evidence_hint"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _run_cleanup(repo: Path, manifest: Path, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--manifest",
            str(manifest.relative_to(repo)),
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cleanup_validation_db_artifacts_dry_run_keeps_file(tmp_path: Path) -> None:
    repo = tmp_path
    db_path = repo / "exports" / "validation" / "run" / "app_copy.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"copied-db")
    manifest = repo / "manifests" / "batch.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/run/app_copy.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "CANDIDATE_COPIED_TEMP_DB",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )

    completed = _run_cleanup(repo, manifest)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "DRY_RUN"
    assert payload["eligible_count"] == 1
    assert payload["blocked_count"] == 0
    assert db_path.exists()


def test_cleanup_validation_db_artifacts_rejects_forbidden_class(tmp_path: Path) -> None:
    repo = tmp_path
    db_path = repo / "exports" / "validation" / "run" / "pre_apply_backup.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"backup")
    manifest = repo / "manifests" / "batch.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/run/pre_apply_backup.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "EXCLUDE_PRODUCTION_OR_APPLY_BACKUP",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )

    completed = _run_cleanup(repo, manifest)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["eligible_count"] == 0
    assert payload["blocked_count"] == 1
    assert "class_not_allowed" in payload["blocked"][0]["errors"][0]
    assert db_path.exists()


def test_cleanup_validation_db_artifacts_rejects_apply_backup_even_if_class_lies(tmp_path: Path) -> None:
    repo = tmp_path
    db_path = (
        repo
        / "exports"
        / "validation"
        / "db_order_entry_owner_apply"
        / "backup"
        / "app_pre_apply.db"
    )
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"backup")
    manifest = repo / "manifests" / "batch.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/db_order_entry_owner_apply/backup/app_pre_apply.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "CANDIDATE_COPIED_DB_BACKUP",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )

    completed = _run_cleanup(repo, manifest)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["eligible_count"] == 0
    assert payload["blocked_count"] == 1
    assert "forbidden_path_part" in payload["blocked"][0]["errors"]
    assert db_path.exists()


def test_cleanup_validation_db_artifacts_apply_requires_env_gate(tmp_path: Path) -> None:
    repo = tmp_path
    db_path = repo / "exports" / "validation" / "run" / "app_copy.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"copied-db")
    manifest = repo / "manifests" / "batch.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/run/app_copy.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "CANDIDATE_COPIED_TEMP_DB",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )

    completed = _run_cleanup(repo, manifest, "--apply")

    assert completed.returncode == 2
    assert "ENABLE_VALIDATION_DB_CLEANUP_DELETE=1 is required" in completed.stderr
    assert db_path.exists()


def test_cleanup_validation_db_artifacts_apply_deletes_and_writes_manifest(tmp_path: Path) -> None:
    repo = tmp_path
    db_path = repo / "exports" / "validation" / "run" / "app_copy.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"copied-db")
    manifest = repo / "manifests" / "batch.tsv"
    deletion_manifest = repo / "exports" / "validation" / "cleanup_manifests" / "deleted.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/run/app_copy.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "CANDIDATE_COPIED_TEMP_DB",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )
    env = {**os.environ, "ENABLE_VALIDATION_DB_CLEANUP_DELETE": "1"}

    completed = _run_cleanup(
        repo,
        manifest,
        "--apply",
        "--deletion-manifest-out",
        str(deletion_manifest.relative_to(repo)),
        env=env,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "APPLY"
    assert payload["deleted_count"] == 1
    assert not db_path.exists()
    rows = list(csv.DictReader(deletion_manifest.open(encoding="utf-8"), delimiter="\t"))
    assert rows[0]["path"] == "exports/validation/run/app_copy.db"
    assert rows[0]["status"] == "deleted"
    assert rows[0]["sha256_before_delete"]
