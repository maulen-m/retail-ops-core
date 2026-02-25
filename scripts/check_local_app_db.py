#!/usr/bin/env python3
"""Fail-closed preflight for the active local SQLite DB file."""

from __future__ import annotations

import argparse
import platform
import sqlite3
import subprocess
from pathlib import Path


def _ls_flags_text(path: Path) -> str:
    """Best-effort `ls -lO` output (macOS file flags including dataless)."""
    if platform.system() != "Darwin":
        return ""
    try:
        result = subprocess.run(
            ["/bin/ls", "-lO", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    return (result.stdout or result.stderr or "").strip()


def _contains_dataless_flag(ls_flags_text: str) -> bool:
    return "dataless" in ls_flags_text.lower()


def validate_local_db(db_path: Path) -> list[str]:
    """Return validation errors; empty list means PASS."""
    errors: list[str] = []

    if db_path.is_symlink():
        target = db_path.resolve(strict=False)
        errors.append(
            f"db path is symlink (unsupported for active DB): {db_path} -> {target}"
        )
        return errors

    if not db_path.exists():
        errors.append(f"db path does not exist: {db_path}")
        return errors

    if not db_path.is_file():
        errors.append(f"db path is not a regular file: {db_path}")
        return errors

    flags_text = _ls_flags_text(db_path)
    if _contains_dataless_flag(flags_text):
        errors.append(f"db file is iCloud dataless placeholder: {db_path}")
        return errors

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        conn.close()
    except Exception as exc:
        errors.append(f"sqlite open failed for {db_path}: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=Path("db/app.db"))
    args = parser.parse_args()

    errors = validate_local_db(args.db_path)
    if errors:
        print("DB preflight: FAIL")
        for err in errors:
            print(f"- {err}")
        print("Fix: use a local regular SQLite file at db/app.db (no symlink/dataless).")
        return 1

    print(f"DB preflight: PASS ({args.db_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
