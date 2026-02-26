from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import run_write_canary as write_canary_mod


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


def test_prod_db_requires_backup_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    def fail_copy(_src: Path, _dst: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(write_canary_mod.shutil, "copy2", fail_copy)

    with pytest.raises(RuntimeError, match="backup creation failed"):
        write_canary_mod.run_write_canary(
            db_path=db_path,
            output_root=tmp_path / "exports",
            as_of="2026-02-26",
            mode="prod_db",
            apply=False,
            strict=True,
        )
