#!/usr/bin/env python3
"""Remove legacy mutable-key UNIQUE constraints from sales projections.

Migration 031 installs entry/article identity indexes. The older table-level
constraints still key rows by mutable SKU, size, or display offer name and can
reject two genuine immutable entry lines. This backup-first migration rebuilds
only sales_fact_v2 and fact_sales while preserving their rows, explicit indexes,
and triggers.

Dry-run is default. Apply requires both ENABLE_SCHEMA_WRITE=1 and
ENABLE_SALES_PUBLIC_LINE_SCHEMA_REBUILD=1, an exact pre-SHA, and a backup dir.
Production additionally requires ENABLE_PRODUCTION_SALES_PUBLIC_LINE_SCHEMA_REBUILD=1.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"

TARGETS = {
    "sales_fact_v2": re.compile(
        r",\s*(?:--[^\n]*\n\s*)*UNIQUE\s*\(\s*order_id\s*,\s*sku_id\s*,\s*store_code\s*,\s*kaspi_offer_name\s*\)",
        re.IGNORECASE,
    ),
    "fact_sales": re.compile(
        r",\s*(?:--[^\n]*\n\s*)*UNIQUE\s*\(\s*order_id\s*,\s*kaspi_offer_name\s*,\s*sku_id\s*,\s*store_code\s*\)",
        re.IGNORECASE,
    ),
}

REQUIRED_LINE_INDEXES = {
    "sales_fact_v2": {
        "ux_sales_fact_v2_source_entry_id",
        "ux_sales_fact_v2_order_store_article_fallback",
        "ux_sales_fact_v2_order_store_line_identity",
    },
    "fact_sales": {
        "ux_fact_sales_source_entry_id",
        "ux_fact_sales_order_store_article_fallback",
        "ux_fact_sales_order_store_line_identity",
    },
}


class MutableUniqueMigrationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not row or not row[0]:
        raise MutableUniqueMigrationError(f"required table missing: {table}")
    return str(row[0])


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _explicit_schema_objects(conn: sqlite3.Connection, table: str) -> list[tuple[str, str, str]]:
    return [
        (str(row[0]), str(row[1]), str(row[2]))
        for row in conn.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE tbl_name=? AND type IN ('index', 'trigger') AND sql IS NOT NULL
            ORDER BY CASE type WHEN 'index' THEN 0 ELSE 1 END, name
            """,
            (table,),
        )
    ]


def _all_views(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return [
        (str(row[0]), str(row[1]))
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='view' AND sql IS NOT NULL ORDER BY rowid"
        )
    ]


def _view_schema_hash(conn: sqlite3.Connection) -> dict[str, Any]:
    views = sorted(_all_views(conn), key=lambda item: item[0])
    digest = hashlib.sha256()
    for name, sql in views:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sql.encode("utf-8"))
        digest.update(b"\n")
    return {"view_count": len(views), "logical_sha256": digest.hexdigest()}


def _logical_hash(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    columns = _columns(conn, table)
    pk_columns = [
        (int(row[5]), str(row[1]))
        for row in conn.execute(f'PRAGMA table_info("{table}")')
        if int(row[5]) > 0
    ]
    if not pk_columns:
        raise MutableUniqueMigrationError(f"table has no primary key: {table}")
    order_by = ",".join(f'"{name}"' for _, name in sorted(pk_columns))
    select_columns = ",".join(f'"{name}"' for name in columns)
    digest = hashlib.sha256()
    count = 0
    for row in conn.execute(
        f'SELECT {select_columns} FROM "{table}" ORDER BY {order_by}'
    ):
        digest.update(
            json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), default=str).encode(
                "utf-8"
            )
        )
        digest.update(b"\n")
        count += 1
    return {"row_count": count, "logical_sha256": digest.hexdigest()}


def _migration_state(conn: sqlite3.Connection) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for table, pattern in TARGETS.items():
        sql = _table_sql(conn, table)
        matches = pattern.findall(sql)
        columns = set(_columns(conn, table))
        indexes = {
            str(row[1]) for row in conn.execute(f'PRAGMA index_list("{table}")')
        }
        state[table] = {
            "legacy_mutable_unique_count": len(matches),
            "source_line_columns_present": {
                "source_entry_id",
                "kaspi_article",
                "line_identity_key",
            }.issubset(columns),
            "missing_source_line_indexes": sorted(REQUIRED_LINE_INDEXES[table] - indexes),
            "logical": _logical_hash(conn, table),
        }
    state["_views"] = _view_schema_hash(conn)
    return state


def _validate_ready_state(state: dict[str, Any]) -> None:
    errors: list[str] = []
    for table, payload in state.items():
        if table.startswith("_"):
            continue
        if not payload["source_line_columns_present"]:
            errors.append(f"{table} lacks migration-031 source-line columns")
        if payload["missing_source_line_indexes"]:
            errors.append(
                f"{table} missing source-line indexes: "
                f"{payload['missing_source_line_indexes']}"
            )
    if errors:
        raise MutableUniqueMigrationError("; ".join(errors))


def _rebuild_table(conn: sqlite3.Connection, table: str, pattern: re.Pattern[str]) -> None:
    original_sql = _table_sql(conn, table)
    replacement_sql, replacements = pattern.subn("", original_sql)
    if replacements != 1:
        raise MutableUniqueMigrationError(
            f"expected exactly one legacy mutable UNIQUE constraint in {table}; got {replacements}"
        )
    objects = _explicit_schema_objects(conn, table)
    columns = _columns(conn, table)
    temp_table = f"{table}__source_line_rebuild"
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (temp_table,)
    ).fetchone():
        raise MutableUniqueMigrationError(f"stale temp table exists: {temp_table}")
    first_paren = replacement_sql.find("(")
    if first_paren < 0:
        raise MutableUniqueMigrationError(f"could not parse CREATE TABLE SQL for {table}")
    create_temp_sql = f'CREATE TABLE "{temp_table}" ' + replacement_sql[first_paren:]
    conn.execute(create_temp_sql)
    column_sql = ",".join(f'"{column}"' for column in columns)
    conn.execute(
        f'INSERT INTO "{temp_table}" ({column_sql}) SELECT {column_sql} FROM "{table}"'
    )
    conn.execute(f'DROP TABLE "{table}"')
    conn.execute(f'ALTER TABLE "{temp_table}" RENAME TO "{table}"')
    for object_type, name, sql in objects:
        try:
            conn.execute(sql)
        except sqlite3.Error as exc:
            raise MutableUniqueMigrationError(
                f"failed to restore {object_type} {name} on {table}: {exc}"
            ) from exc


def _backup_db(db_path: Path, backup_dir: Path, pre_sha: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"{db_path.stem}_before_migration_032_{stamp}_{pre_sha[:12]}.db"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    source_conn = sqlite3.connect(str(db_path))
    backup_conn = sqlite3.connect(str(path))
    try:
        integrity = str(backup_conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise MutableUniqueMigrationError(
                f"backup integrity check failed: {integrity}"
            )
        for table in TARGETS:
            if _logical_hash(source_conn, table) != _logical_hash(backup_conn, table):
                raise MutableUniqueMigrationError(
                    f"backup logical readback mismatch: {table}"
                )
    finally:
        backup_conn.close()
        source_conn.close()
    return path


def run(
    *,
    db_path: Path,
    apply: bool,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
) -> dict[str, Any]:
    if not db_path.is_file():
        raise MutableUniqueMigrationError(f"database not found: {db_path}")
    pre_sha = _sha256(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        before = _migration_state(conn)
        _validate_ready_state(before)
        required = [
            table
            for table, payload in before.items()
            if not table.startswith("_")
            if payload["legacy_mutable_unique_count"] == 1
        ]
        unexpected = [
            table
            for table, payload in before.items()
            if not table.startswith("_")
            if payload["legacy_mutable_unique_count"] not in {0, 1}
        ]
        if unexpected:
            raise MutableUniqueMigrationError(
                f"unexpected legacy constraint cardinality: {unexpected}"
            )
        report: dict[str, Any] = {
            "mode": "dry_run",
            "db_path": str(db_path.resolve()),
            "pre_sha256": pre_sha,
            "migration_required_tables": required,
            "before": before,
            "production_write_authorized": False,
        }
        if not apply or not required:
            report["mode"] = "already_migrated_noop" if not required else "dry_run"
            report["post_sha256"] = pre_sha
            return report

        if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
            raise MutableUniqueMigrationError("ENABLE_SCHEMA_WRITE=1 is required for --apply")
        if os.environ.get("ENABLE_SALES_PUBLIC_LINE_SCHEMA_REBUILD") != "1":
            raise MutableUniqueMigrationError(
                "ENABLE_SALES_PUBLIC_LINE_SCHEMA_REBUILD=1 is required for --apply"
            )
        if db_path.resolve() == DEFAULT_DB.resolve() and os.environ.get(
            "ENABLE_PRODUCTION_SALES_PUBLIC_LINE_SCHEMA_REBUILD"
        ) != "1":
            raise MutableUniqueMigrationError(
                "production apply is not authorized; missing "
                "ENABLE_PRODUCTION_SALES_PUBLIC_LINE_SCHEMA_REBUILD=1"
            )
        if not expected_pre_sha256 or pre_sha != expected_pre_sha256:
            raise MutableUniqueMigrationError(
                f"exact --expected-pre-sha256 is required; observed={pre_sha} "
                f"expected={expected_pre_sha256}"
            )
        if backup_dir is None:
            raise MutableUniqueMigrationError("--backup-dir is required for --apply")
        backup_path = _backup_db(db_path, backup_dir, pre_sha)

        views = _all_views(conn)
        conn.execute("BEGIN IMMEDIATE")
        for view_name, _view_sql in reversed(views):
            conn.execute(f'DROP VIEW "{view_name.replace(chr(34), chr(34) * 2)}"')
        for table in required:
            _rebuild_table(conn, table, TARGETS[table])
        for _view_name, view_sql in views:
            conn.execute(view_sql)
        after = _migration_state(conn)
        for table in TARGETS:
            if after[table]["legacy_mutable_unique_count"] != 0:
                raise MutableUniqueMigrationError(
                    f"legacy mutable UNIQUE constraint remains on {table}"
                )
            if after[table]["logical"] != before[table]["logical"]:
                raise MutableUniqueMigrationError(f"row hash changed while rebuilding {table}")
            if after[table]["missing_source_line_indexes"]:
                raise MutableUniqueMigrationError(
                    f"source-line indexes not restored on {table}: "
                    f"{after[table]['missing_source_line_indexes']}"
                )
        if after["_views"] != before["_views"]:
            raise MutableUniqueMigrationError(
                f"view schema changed during table rebuild: "
                f"before={before['_views']} after={after['_views']}"
            )
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        if integrity != "ok" or quick != "ok":
            raise MutableUniqueMigrationError(
                f"database checks failed: integrity={integrity} quick={quick}"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    report.update(
        {
            "mode": "applied",
            "backup_path": str(backup_path.resolve()),
            "backup_sha256": _sha256(backup_path),
            "post_sha256": _sha256(db_path),
            "after": after,
            "integrity_check": integrity,
            "quick_check": quick,
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = run(
            db_path=args.db,
            apply=bool(args.apply),
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir,
        )
    except MutableUniqueMigrationError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
