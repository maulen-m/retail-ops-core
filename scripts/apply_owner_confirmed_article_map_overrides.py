#!/usr/bin/env python3
"""Apply narrow owner-confirmed Kaspi article-map overrides.

Default is dry-run. Apply requires ENABLE_OWNER_CONFIRMED_ARTICLE_MAP_WRITE=1
and --apply. This script intentionally contains only reviewed, explicit
owner-confirmed rows so it cannot become a broad catalog rewrite surface.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402

ENV_GATE = "ENABLE_OWNER_CONFIRMED_ARTICLE_MAP_WRITE"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "owner_confirmed_article_map_overrides"

OWNER_CONFIRMED_OVERRIDES = [
    {
        "store_code": "UNIVERSAL",
        "merchant_id": "30000001",
        "kaspi_article": "132822924_328581041",
        "kaspi_offer_name": "Леггинсы PRO COMBAT 2010 белый XL",
        "kaspi_name_core": "Леггинсы_белый",
        "sku_key": "CL_NEW-CLO_MEN_LEG_WHITE",
        "sku_id": "CL_NEW-CLO_MEN_LEG_WHITE_XL",
        "model": "LEG",
        "brand": "New-Clo",
        "source": "OWNER_CONFIRMED_2026_05_21_UNIVERSAL_132822924_328581041",
    }
]


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _backup_db(db_path: Path, output_root: Path) -> Path:
    backup_dir = output_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_before_owner_article_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _fetch_existing(conn: sqlite3.Connection, store_code: str, kaspi_article: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM dim_kaspi_article_map
        WHERE UPPER(store_code) = UPPER(?)
          AND kaspi_article = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (store_code, kaspi_article),
    ).fetchone()
    return dict(row) if row else None


def _upsert_override(conn: sqlite3.Connection, override: dict[str, str]) -> dict[str, Any]:
    columns = _table_columns(conn, "dim_kaspi_article_map")
    existing = _fetch_existing(conn, override["store_code"], override["kaspi_article"])
    writable = {
        key: value
        for key, value in override.items()
        if key in columns
    }
    if "active_flag" in columns:
        writable["active_flag"] = 1
    if "updated_at" in columns:
        writable["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if existing:
        assignments = ", ".join(f"{col}=?" for col in writable)
        conn.execute(
            f"""
            UPDATE dim_kaspi_article_map
            SET {assignments}
            WHERE id = ?
            """,
            [*writable.values(), existing["id"]],
        )
        action = "UPDATE"
    else:
        if "created_at" in columns:
            writable["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cols = ", ".join(writable.keys())
        placeholders = ", ".join("?" for _ in writable)
        conn.execute(
            f"INSERT INTO dim_kaspi_article_map ({cols}) VALUES ({placeholders})",
            list(writable.values()),
        )
        action = "INSERT"

    after = _fetch_existing(conn, override["store_code"], override["kaspi_article"])
    return {
        "action": action,
        "before": existing,
        "after": after,
    }


def run(*, db_path: Path, output_root: Path, apply: bool) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if apply and os.environ.get(ENV_GATE) != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required with --apply")

    backup_path: Path | None = None
    if apply:
        backup_path = _backup_db(db_path, output_root)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "dim_kaspi_article_map"):
            raise RuntimeError("dim_kaspi_article_map missing")
        before = [
            _fetch_existing(conn, row["store_code"], row["kaspi_article"])
            for row in OWNER_CONFIRMED_OVERRIDES
        ]
        changes: list[dict[str, Any]] = []
        if apply:
            for row in OWNER_CONFIRMED_OVERRIDES:
                changes.append(_upsert_override(conn, row))
            conn.commit()
        else:
            conn.rollback()
        after = [
            _fetch_existing(conn, row["store_code"], row["kaspi_article"])
            for row in OWNER_CONFIRMED_OVERRIDES
        ]
    finally:
        conn.close()

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "db_path": str(db_path),
        "apply_status": "APPLIED" if apply else "DRY_RUN",
        "env_gate": ENV_GATE,
        "backup_path": str(backup_path) if backup_path else None,
        "override_count": len(OWNER_CONFIRMED_OVERRIDES),
        "before": before,
        "after": after,
        "changes": changes,
        "rollback": {
            "backup_path": str(backup_path) if backup_path else None,
            "restore_command": f"cp {backup_path} {db_path}" if backup_path else None,
        },
    }
    summary_path = output_root / "owner_confirmed_article_map_overrides_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary["summary_json"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    summary = run(db_path=args.db, output_root=args.output_root, apply=bool(args.apply))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
