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
        conn.execute("INSERT INTO source_rows (name) VALUES ('seed')")
        conn.commit()
    finally:
        conn.close()


def _count_canary_rows(path: Path, key: str) -> int:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS write_canary_log (
                marker TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                details TEXT
            )
            """
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM write_canary_log WHERE marker LIKE ?",
            (f"{key}:%",),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def test_prod_db_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_PROD_DB_CANARY_WRITE=1"):
        run_write_canary(
            db_path=db_path,
            output_root=tmp_path / "exports",
            as_of="2026-02-26",
            mode="prod_db",
            apply=True,
            strict=True,
            env=os.environ,
        )


def test_prod_db_dry_run_does_not_write(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    key = "H3_PROD_DRY"

    report = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        mode="prod_db",
        apply=False,
        strict=True,
        idempotence_key=key,
    )

    assert report["ok"] is True
    assert report["mode"] == "prod_db"
    assert report["apply_mode"] == "dry-run"
    assert report["inserted_rows"] == 0
    assert _count_canary_rows(db_path, key) == 0


def test_prod_db_apply_is_idempotent_when_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    key = "H3_PROD_APPLY"
    monkeypatch.setenv("ENABLE_PROD_DB_CANARY_WRITE", "1")

    report_1 = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        mode="prod_db",
        apply=True,
        strict=True,
        max_rows=2,
        idempotence_key=key,
        env=os.environ,
    )
    report_2 = run_write_canary(
        db_path=db_path,
        output_root=tmp_path / "exports",
        as_of="2026-02-26",
        mode="prod_db",
        apply=True,
        strict=True,
        max_rows=2,
        idempotence_key=key,
        env=os.environ,
    )

    assert report_1["inserted_rows"] == 2
    assert report_2["inserted_rows"] == 0
    assert _count_canary_rows(db_path, key) == 2
