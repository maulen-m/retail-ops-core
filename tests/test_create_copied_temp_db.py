from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


SCRIPT = Path("scripts/create_copied_temp_db.py")


def _seed_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO sample (name) VALUES ('ok')")
        connection.commit()
    finally:
        connection.close()


def _run(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--json", *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_create_copied_temp_db_dry_run_does_not_copy(tmp_path: Path) -> None:
    source = tmp_path / "db" / "app.db"
    run_root = tmp_path / "run"
    run_root.mkdir()
    _seed_db(source)

    completed = _run(
        tmp_path,
        "--source-db",
        str(source.relative_to(tmp_path)),
        "--run-root",
        str(run_root.relative_to(tmp_path)),
        "--db-name",
        "copy.db",
        "--min-free-gib",
        "0",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "DRY_RUN"
    assert payload["ok"] is True
    assert not (run_root / "copy.db").exists()


def test_create_copied_temp_db_copy_writes_manifest_and_integrity(tmp_path: Path) -> None:
    source = tmp_path / "db" / "app.db"
    run_root = tmp_path / "run"
    manifest = run_root / "copy_manifest.json"
    run_root.mkdir()
    _seed_db(source)

    completed = _run(
        tmp_path,
        "--source-db",
        str(source.relative_to(tmp_path)),
        "--run-root",
        str(run_root.relative_to(tmp_path)),
        "--db-name",
        "copy.db",
        "--min-free-gib",
        "0",
        "--manifest-out",
        str(manifest.relative_to(tmp_path)),
        "--copy",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "COPIED_TEMP_DB_READY"
    assert payload["source_sha256"] == payload["target_sha256"]
    assert payload["sqlite_integrity_check"] == "ok"
    assert (run_root / "copy.db").exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["target_db"] == str(run_root / "copy.db")


def test_create_copied_temp_db_blocks_missing_run_root(tmp_path: Path) -> None:
    source = tmp_path / "db" / "app.db"
    _seed_db(source)

    completed = _run(
        tmp_path,
        "--source-db",
        str(source.relative_to(tmp_path)),
        "--run-root",
        "missing",
        "--db-name",
        "copy.db",
        "--min-free-gib",
        "0",
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert "FAIL_RUNWAY_PATH_MISSING" in payload["errors"]


def test_create_copied_temp_db_blocks_target_escape(tmp_path: Path) -> None:
    source = tmp_path / "db" / "app.db"
    run_root = tmp_path / "run"
    run_root.mkdir()
    _seed_db(source)

    completed = _run(
        tmp_path,
        "--source-db",
        str(source.relative_to(tmp_path)),
        "--run-root",
        str(run_root.relative_to(tmp_path)),
        "--db-name",
        "../escape.db",
        "--min-free-gib",
        "0",
    )

    assert completed.returncode == 2
    assert "target escapes run root" in completed.stderr
