#!/usr/bin/env python3
"""
Migration 030: make fact_orders_kaspi line-grained by public offer identity.

Default: dry-run.
Apply requires ENABLE_SCHEMA_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

TABLE = "fact_orders_kaspi"
OLD_UNIQUE_COLUMNS = ("order_id", "sku_id", "store_code")
LINE_GRAIN_UNIQUE_COLUMNS = ("order_id", "store_code", "line_identity_key", "sku_id")
BACKUP_TABLE = "fact_orders_kaspi__pre_line_grain_migration"


def _quote_ident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall())


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in _table_info(conn, table)]


def _index_columns(conn: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({_quote_ident(index_name)})").fetchall()
    return tuple(str(row["name"]) for row in rows)


def _has_unique_index(conn: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> bool:
    for row in conn.execute(f"PRAGMA index_list({_quote_ident(table)})").fetchall():
        if int(row["unique"] or 0) != 1:
            continue
        if _index_columns(conn, str(row["name"])) == columns:
            return True
    return False


def _saved_index_sql(conn: sqlite3.Connection) -> list[str]:
    saved: list[str] = []
    for row in conn.execute(f"PRAGMA index_list({_quote_ident(TABLE)})").fetchall():
        index_name = str(row["name"])
        if int(row["unique"] or 0) == 1 and _index_columns(conn, index_name) == OLD_UNIQUE_COLUMNS:
            continue
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
        sql = str(sql_row["sql"] or "").strip() if sql_row else ""
        if sql:
            saved.append(sql)
    return saved


def _saved_trigger_sql(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type='trigger' AND tbl_name=?
        ORDER BY name
        """,
        (TABLE,),
    ).fetchall()
    return [str(row["sql"]).strip() for row in rows if str(row["sql"] or "").strip()]


def _column_def(row: sqlite3.Row) -> str:
    name = str(row["name"])
    col_type = str(row["type"] or "").strip()
    parts = [_quote_ident(name)]
    if col_type:
        parts.append(col_type)
    if int(row["pk"] or 0):
        parts.append("PRIMARY KEY")
    elif int(row["notnull"] or 0):
        parts.append("NOT NULL")
    if row["dflt_value"] is not None:
        parts.append(f"DEFAULT {row['dflt_value']}")
    return " ".join(parts)


def _line_identity_expr(existing_columns: set[str]) -> str:
    parts: list[str] = []
    if "kaspi_article" in existing_columns:
        parts.append("NULLIF(kaspi_article, '')")
    if "kaspi_offer_name" in existing_columns:
        parts.append("NULLIF(kaspi_offer_name, '')")
    if "sku_id" in existing_columns:
        parts.append("NULLIF(sku_id, '')")
    if "id" in existing_columns:
        parts.append("printf('legacy-row:%s', id)")
    parts.append("''")
    return f"COALESCE({', '.join(parts)})"


def validate_line_grain_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, TABLE):
            return [f"Missing table: {TABLE}"]
        columns = set(_table_columns(conn, TABLE))
        if "kaspi_article" not in columns:
            errors.append("Missing column: fact_orders_kaspi.kaspi_article")
        if "line_identity_key" not in columns:
            errors.append("Missing column: fact_orders_kaspi.line_identity_key")
        if not _has_unique_index(conn, TABLE, LINE_GRAIN_UNIQUE_COLUMNS):
            errors.append(
                "Missing unique line-grain key: "
                "fact_orders_kaspi(order_id, store_code, line_identity_key, sku_id)"
            )
        if _has_unique_index(conn, TABLE, OLD_UNIQUE_COLUMNS):
            errors.append(
                "Blocking old unique key still present: fact_orders_kaspi(order_id, sku_id, store_code)"
            )
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, TABLE):
            raise RuntimeError(f"{TABLE} table is missing; run base schema migration first")
        if not validate_line_grain_schema(db_path):
            return

        conn.execute("BEGIN")
        if _table_exists(conn, BACKUP_TABLE):
            conn.execute(f"DROP TABLE {_quote_ident(BACKUP_TABLE)}")

        original_info = _table_info(conn, TABLE)
        original_columns = [str(row["name"]) for row in original_info]
        original_column_set = set(original_columns)
        index_sql = _saved_index_sql(conn)
        trigger_sql = _saved_trigger_sql(conn)

        conn.execute(f"ALTER TABLE {_quote_ident(TABLE)} RENAME TO {_quote_ident(BACKUP_TABLE)}")

        column_defs = [_column_def(row) for row in original_info]
        if "kaspi_article" not in original_column_set:
            column_defs.append('"kaspi_article" TEXT')
        if "line_identity_key" not in original_column_set:
            column_defs.append('"line_identity_key" TEXT NOT NULL DEFAULT \'\'')
        column_defs.append(
            'UNIQUE("order_id", "store_code", "line_identity_key", "sku_id")'
        )
        conn.execute(
            f"""
            CREATE TABLE {_quote_ident(TABLE)} (
                {", ".join(column_defs)}
            )
            """
        )

        target_columns = _table_columns(conn, TABLE)
        select_exprs: list[str] = []
        line_expr = _line_identity_expr(original_column_set)
        for column in target_columns:
            if column in original_column_set and column == "line_identity_key":
                select_exprs.append(f"COALESCE(NULLIF({_quote_ident(column)}, ''), {line_expr})")
            elif column in original_column_set:
                select_exprs.append(_quote_ident(column))
            elif column == "kaspi_article":
                select_exprs.append("''")
            elif column == "line_identity_key":
                select_exprs.append(line_expr)
            else:
                select_exprs.append("NULL")

        target_sql = ", ".join(_quote_ident(column) for column in target_columns)
        select_sql = ", ".join(select_exprs)
        before_count = int(conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(BACKUP_TABLE)}").fetchone()[0])
        conn.execute(
            f"""
            INSERT INTO {_quote_ident(TABLE)} ({target_sql})
            SELECT {select_sql}
            FROM {_quote_ident(BACKUP_TABLE)}
            """
        )
        after_count = int(conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(TABLE)}").fetchone()[0])
        if before_count != after_count:
            raise RuntimeError(f"row-count mismatch during migration: before={before_count} after={after_count}")

        conn.execute(f"DROP TABLE {_quote_ident(BACKUP_TABLE)}")
        for sql in index_sql:
            conn.execute(sql)
        for sql in trigger_sql:
            conn.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate fact_orders_kaspi to public-offer line grain")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply:
        errors = validate_line_grain_schema(args.db)
        if errors:
            print("DRY RUN: fact_orders_kaspi line-grain migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: fact_orders_kaspi line-grain schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    errors = validate_line_grain_schema(args.db)
    if errors:
        print("ERROR: fact_orders_kaspi line-grain migration incomplete:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("fact_orders_kaspi line-grain migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
