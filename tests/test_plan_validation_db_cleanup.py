from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/plan_validation_db_cleanup.py")


def _write_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_plan_validation_db_cleanup_writes_manifest_and_batch(tmp_path: Path) -> None:
    repo = tmp_path
    validation = repo / "exports" / "validation"
    _write_file(validation / "wave" / "copied_db" / "app_copy.db", b"a" * 10)
    _write_file(validation / "wave" / "copied_db" / "app_copy.sha256", b"sha")
    _write_file(validation / "wave" / "backups" / "app_before.db", b"b" * 20)
    _write_file(validation / "wave" / "VALIDATOR_EXIT_MATRIX.tsv", b"validator")
    _write_file(validation / "db_order_entry_owner_apply" / "backup" / "app_pre_apply.db", b"c" * 30)
    manifest = repo / "out" / "manifest.tsv"
    batch = repo / "out" / "batch.tsv"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--manifest-out",
            str(manifest.relative_to(repo)),
            "--first-batch-out",
            str(batch.relative_to(repo)),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["row_count"] == 3
    assert summary["first_batch_count"] == 2
    manifest_rows = list(csv.DictReader(manifest.open(encoding="utf-8"), delimiter="\t"))
    batch_rows = list(csv.DictReader(batch.open(encoding="utf-8"), delimiter="\t"))
    classes = {row["class"] for row in manifest_rows}
    assert "EXCLUDE_PRODUCTION_OR_APPLY_BACKUP" in classes
    assert {row["class"] for row in batch_rows} == {
        "CANDIDATE_COPIED_DB_BACKUP",
        "CANDIDATE_COPIED_TEMP_DB",
    }


def test_plan_validation_db_cleanup_first_batch_requires_evidence_hint(tmp_path: Path) -> None:
    repo = tmp_path
    validation = repo / "exports" / "validation"
    _write_file(validation / "no_evidence" / "app_copy.db", b"a" * 100)
    batch = repo / "out" / "batch.tsv"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--first-batch-out",
            str(batch.relative_to(repo)),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    rows = list(csv.DictReader(batch.open(encoding="utf-8"), delimiter="\t"))
    assert rows == []
