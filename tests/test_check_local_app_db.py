import sqlite3
from pathlib import Path

from scripts.check_local_app_db import _contains_dataless_flag, validate_local_db


def _make_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()


def test_validate_local_db_passes_for_regular_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "ok.sqlite"
    _make_sqlite(db_path)
    assert validate_local_db(db_path) == []


def test_validate_local_db_fails_for_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.sqlite"
    _make_sqlite(target)
    link = tmp_path / "app.db"
    link.symlink_to(target)
    errors = validate_local_db(link)
    assert errors
    assert "symlink" in errors[0]


def test_validate_local_db_fails_for_invalid_sqlite(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite"
    bad.write_text("not a sqlite db", encoding="utf-8")
    errors = validate_local_db(bad)
    assert errors
    assert "sqlite open failed" in errors[0]


def test_contains_dataless_flag_detection() -> None:
    assert _contains_dataless_flag("-rw-r--r--  compressed,dataless 123 file.sqlite")
    assert not _contains_dataless_flag("-rw-r--r-- - 123 file.sqlite")
