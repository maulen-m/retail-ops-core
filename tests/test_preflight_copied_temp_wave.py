from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/preflight_copied_temp_wave.py")


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "size_bytes", "size_mib", "class", "evidence_hint"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _run_preflight(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--skip-db-guard",
            "--skip-source-contract-registry",
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_preflight_copied_temp_wave_passes_with_zero_disk_threshold(tmp_path: Path) -> None:
    completed = _run_preflight(tmp_path, "--min-free-gib", "0")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["status"] == "PASS"
    assert [check["id"] for check in payload["checks"]] == [
        "validation_disk_runway",
        "db_guard",
        "source_contract_registry",
    ]


def test_preflight_copied_temp_wave_fails_low_disk(tmp_path: Path) -> None:
    completed = _run_preflight(tmp_path, "--min-free-gib", "999999")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    disk_check = payload["checks"][0]
    assert disk_check["id"] == "validation_disk_runway"
    assert disk_check["status"] == "FAIL_LOW_DISK_RUNWAY"


def test_preflight_copied_temp_wave_checks_run_root_separately(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_root = tmp_path / "run_root"
    repo.mkdir()
    run_root.mkdir()

    completed = _run_preflight(
        repo,
        "--run-root",
        str(run_root),
        "--min-free-gib",
        "0",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["repo"] == str(repo)
    assert payload["run_root"] == str(run_root)
    disk_check = payload["checks"][0]
    assert disk_check["details"]["path"] == str(run_root)


def test_preflight_copied_temp_wave_blocks_missing_run_root(tmp_path: Path) -> None:
    missing_run_root = tmp_path / "missing_run_root"
    completed = _run_preflight(
        tmp_path,
        "--run-root",
        str(missing_run_root),
        "--min-free-gib",
        "0",
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    disk_check = payload["checks"][0]
    assert disk_check["status"] == "FAIL_RUNWAY_PATH_MISSING"
    assert disk_check["details"]["path_exists"] is False


def test_preflight_copied_temp_wave_accepts_clean_cleanup_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "exports" / "validation" / "run" / "app_copy.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"db")
    manifest = tmp_path / "manifests" / "batch.tsv"
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

    completed = _run_preflight(
        tmp_path,
        "--min-free-gib",
        "0",
        "--cleanup-manifest",
        str(manifest.relative_to(tmp_path)),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    cleanup_check = payload["checks"][1]
    assert cleanup_check["id"] == "cleanup_manifest_dry_run"
    assert cleanup_check["status"] == "PASS"
    assert cleanup_check["details"]["eligible_count"] == 1
    assert db_path.exists()


def test_preflight_copied_temp_wave_blocks_dirty_cleanup_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "exports" / "validation" / "run" / "app_pre_apply.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"db")
    manifest = tmp_path / "manifests" / "batch.tsv"
    _write_manifest(
        manifest,
        [
            {
                "path": "exports/validation/run/app_pre_apply.db",
                "size_bytes": str(db_path.stat().st_size),
                "size_mib": "0.0",
                "class": "EXCLUDE_PRODUCTION_OR_APPLY_BACKUP",
                "evidence_hint": "same_dir_evidence",
            }
        ],
    )

    completed = _run_preflight(
        tmp_path,
        "--min-free-gib",
        "0",
        "--cleanup-manifest",
        str(manifest.relative_to(tmp_path)),
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    cleanup_check = payload["checks"][1]
    assert cleanup_check["status"] == "FAIL_CLEANUP_MANIFEST"
    assert cleanup_check["details"]["blocked_count"] == 1
    assert db_path.exists()
