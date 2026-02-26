from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from scripts.run_write_canary import run_write_canary


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_rows (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO source_rows (name) VALUES ('row-1')")
        conn.commit()
    finally:
        conn.close()


def test_write_canary_dry_run_is_default_and_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    report = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        apply=False,
        strict=True,
    )

    assert report["ok"] is True
    assert report["mode"] == "db_only"
    assert report["apply_mode"] == "dry-run"
    assert report["inserted_rows"] == 0
    assert Path(report["backup_path"]).exists()


def test_write_canary_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_WRITE_CANARY_APPLY"):
        run_write_canary(
            db_path=db_path,
            output_root=tmp_path / "exports",
            as_of="2026-02-26",
            apply=True,
            strict=True,
            env=os.environ,
        )


def test_write_canary_apply_creates_backup_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    monkeypatch.setenv("ENABLE_WRITE_CANARY_APPLY", "1")

    report_1 = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        apply=True,
        strict=True,
        max_rows=3,
        idempotence_key="CANARY_X",
        env=os.environ,
    )
    report_2 = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        apply=True,
        strict=True,
        max_rows=3,
        idempotence_key="CANARY_X",
        env=os.environ,
    )

    assert report_1["ok"] is True
    assert report_1["mode"] == "db_only"
    assert report_1["apply_mode"] == "apply"
    assert report_1["inserted_rows"] == 3
    assert report_2["ok"] is True
    assert report_2["mode"] == "db_only"
    assert report_2["inserted_rows"] == 0
    assert Path(report_1["backup_path"]).exists()
    assert Path(report_1["rollback_proof_path"]).exists()
    assert Path(report_1["diff_json_path"]).exists()
