#!/usr/bin/env python3
"""Migration 031: persist stable source-proven sales line identity.

Immutable API entry ID is strongest. When it is unavailable, the fallback grain
is order + store + public Kaspi article. Size, display name, workbook row, and
lifecycle date are mutable attributes.

Default: dry-run. Apply requires ENABLE_SCHEMA_WRITE=1 and --apply.
This migration does not infer or backfill missing articles.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

ARTICLE_TABLES = ("fact_orders_kaspi", "sales_fact_v2", "fact_sales")
ALL_TABLES = (*ARTICLE_TABLES, "stock_ledger")
STOCK_IDENTITY_TABLE = "stock_ledger_source_identity"

ARTICLE_INDEXES = {
    "fact_orders_kaspi": "ux_fact_orders_kaspi_order_store_article_fallback",
    "sales_fact_v2": "ux_sales_fact_v2_order_store_article_fallback",
    "fact_sales": "ux_fact_sales_order_store_article_fallback",
}
ENTRY_INDEXES = {
    "fact_orders_kaspi": "ux_fact_orders_kaspi_source_entry_id",
    "sales_fact_v2": "ux_sales_fact_v2_source_entry_id",
    "fact_sales": "ux_fact_sales_source_entry_id",
}
LINE_INDEXES = {
    "fact_orders_kaspi": "ux_fact_orders_kaspi_order_store_line_identity",
    "sales_fact_v2": "ux_sales_fact_v2_order_store_line_identity",
    "fact_sales": "ux_fact_sales_order_store_line_identity",
}


def _quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    }


def _index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


def _index_sql(conn: sqlite3.Connection, index_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return str(row[0] or "").upper() if row else ""


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    if column not in _columns(conn, table):
        conn.execute(
            f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(column)} {declaration}"
        )


def _article_duplicate_groups(
    conn: sqlite3.Connection,
    table: str,
) -> list[tuple[str, str, str, int]]:
    rows = conn.execute(
        f"""
        SELECT CAST(order_id AS TEXT) AS order_id,
               UPPER(TRIM(COALESCE(store_code, ''))) AS store_code,
               UPPER(TRIM(kaspi_article)) AS kaspi_article,
               COUNT(*) AS row_count
        FROM {_quote(table)}
        WHERE TRIM(COALESCE(source_entry_id, '')) = ''
          AND TRIM(COALESCE(kaspi_article, '')) <> ''
        GROUP BY CAST(order_id AS TEXT),
                 UPPER(TRIM(COALESCE(store_code, ''))),
                 UPPER(TRIM(kaspi_article))
        HAVING COUNT(*) > 1
        ORDER BY order_id, store_code, kaspi_article
        """
    ).fetchall()
    return [
        (str(row[0]), str(row[1]), str(row[2]), int(row[3]))
        for row in rows
    ]


def _entry_duplicate_count(conn: sqlite3.Connection, table: str) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT TRIM(source_entry_id)
                FROM {_quote(table)}
                WHERE TRIM(COALESCE(source_entry_id, '')) <> ''
                GROUP BY TRIM(source_entry_id)
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )


def _article_identity_mismatch_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {_quote(table)}
            WHERE (
                    TRIM(COALESCE(source_entry_id, '')) <> ''
                AND TRIM(COALESCE(line_identity_key, '')) <>
                    'ENTRY:' || TRIM(source_entry_id)
            ) OR (
                    TRIM(COALESCE(source_entry_id, '')) = ''
                AND TRIM(COALESCE(kaspi_article, '')) <> ''
                AND TRIM(COALESCE(line_identity_key, '')) <>
                    'ARTICLE:' || UPPER(TRIM(kaspi_article))
            )
            """
        ).fetchone()[0]
    )


def _missing_tables(conn: sqlite3.Connection) -> list[str]:
    return [table for table in ALL_TABLES if not _table_exists(conn, table)]


def validate_public_article_line_grain(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        missing = _missing_tables(conn)
        errors.extend(f"Missing table: {table}" for table in missing)
        for table in ALL_TABLES:
            if table in missing:
                continue
            columns = _columns(conn, table)
            for column in ("source_entry_id", "kaspi_article", "line_identity_key"):
                if column not in columns:
                    errors.append(f"Missing column: {table}.{column}")
        for table, index_name in ARTICLE_INDEXES.items():
            if table in missing:
                continue
            columns = _columns(conn, table)
            if {"source_entry_id", "kaspi_article", "line_identity_key"}.issubset(columns):
                duplicate_count = len(_article_duplicate_groups(conn, table))
                if duplicate_count:
                    errors.append(
                        f"Duplicate public-article line groups: {table}={duplicate_count}"
                    )
                mismatch_count = _article_identity_mismatch_count(conn, table)
                if mismatch_count:
                    errors.append(
                        f"Public-article/line-key mismatch rows: {table}={mismatch_count}"
                    )
                entry_duplicate_count = _entry_duplicate_count(conn, table)
                if entry_duplicate_count:
                    errors.append(
                        f"Duplicate source-entry groups: {table}={entry_duplicate_count}"
                    )
            article_sql = _index_sql(conn, index_name)
            if not article_sql:
                errors.append(f"Missing unique article-grain index: {index_name}")
            elif "SOURCE_ENTRY_ID" not in article_sql or "KASPI_ARTICLE" not in article_sql:
                errors.append(f"Wrong article-grain index definition: {index_name}")
            for required_index, required_token in (
                (ENTRY_INDEXES[table], "SOURCE_ENTRY_ID"),
                (LINE_INDEXES[table], "LINE_IDENTITY_KEY"),
            ):
                index_sql = _index_sql(conn, required_index)
                if not index_sql:
                    errors.append(f"Missing source-line index: {required_index}")
                elif required_token not in index_sql:
                    errors.append(f"Wrong source-line index definition: {required_index}")
        if _table_exists(conn, "stock_ledger") and not _index_exists(
            conn, "idx_stock_ledger_order_line_identity"
        ):
            errors.append(
                "Missing stock-ledger line index: idx_stock_ledger_order_line_identity"
            )
        if _table_exists(conn, "stock_ledger"):
            stock_columns = _columns(conn, "stock_ledger")
            for column in (
                "source_entry_id",
                "source_store_code",
                "repair_batch_id",
                "supersedes_ledger_id",
            ):
                if column not in stock_columns:
                    errors.append(f"Missing stock-ledger provenance column: {column}")
            if not _index_exists(conn, "ux_stock_ledger_supersedes_ledger_id"):
                errors.append(
                    "Missing stock-ledger supersession guard: "
                    "ux_stock_ledger_supersedes_ledger_id"
                )
        if not _table_exists(conn, STOCK_IDENTITY_TABLE):
            errors.append(f"Missing table: {STOCK_IDENTITY_TABLE}")
        else:
            identity_columns = _columns(conn, STOCK_IDENTITY_TABLE)
            for column in (
                "ledger_id",
                "source_entry_id",
                "source_store_code",
                "kaspi_article",
                "line_identity_key",
                "repair_batch_id",
            ):
                if column not in identity_columns:
                    errors.append(
                        f"Missing stock-ledger identity column: "
                        f"{STOCK_IDENTITY_TABLE}.{column}"
                    )
    finally:
        conn.close()
    return errors


def _create_article_index(
    conn: sqlite3.Connection,
    table: str,
    index_name: str,
) -> None:
    duplicates = _article_duplicate_groups(conn, table)
    if duplicates:
        preview = ", ".join(
            f"{order}/{store}/{article} x{count}"
            for order, store, article, count in duplicates[:5]
        )
        raise RuntimeError(
            f"cannot create {index_name}; duplicate public-article lines in "
            f"{table}: {preview}"
        )
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_quote(index_name)}
        ON {_quote(table)} (
            CAST(order_id AS TEXT),
            UPPER(TRIM(COALESCE(store_code, ''))),
            UPPER(TRIM(kaspi_article))
        )
        WHERE TRIM(COALESCE(source_entry_id, '')) = ''
          AND TRIM(COALESCE(kaspi_article, '')) <> ''
        """
    )


def _create_source_line_indexes(conn: sqlite3.Connection, table: str) -> None:
    entry_duplicates = _entry_duplicate_count(conn, table)
    if entry_duplicates:
        raise RuntimeError(
            f"cannot create {ENTRY_INDEXES[table]}; duplicate source entries in "
            f"{table}: {entry_duplicates}"
        )
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_quote(ENTRY_INDEXES[table])}
        ON {_quote(table)} (TRIM(source_entry_id))
        WHERE TRIM(COALESCE(source_entry_id, '')) <> ''
        """
    )
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_quote(LINE_INDEXES[table])}
        ON {_quote(table)} (
            CAST(order_id AS TEXT),
            UPPER(TRIM(COALESCE(store_code, ''))),
            TRIM(line_identity_key)
        )
        WHERE TRIM(COALESCE(line_identity_key, '')) <> ''
          AND (
                TRIM(COALESCE(source_entry_id, '')) <> ''
             OR TRIM(COALESCE(kaspi_article, '')) <> ''
          )
        """
    )


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        missing = _missing_tables(conn)
        if missing:
            raise RuntimeError(f"required tables missing: {', '.join(missing)}")
        conn.execute("BEGIN IMMEDIATE")
        for table in ALL_TABLES:
            _ensure_column(conn, table, "source_entry_id", "TEXT")
            _ensure_column(conn, table, "kaspi_article", "TEXT")
            _ensure_column(conn, table, "line_identity_key", "TEXT")

        _ensure_column(conn, "stock_ledger", "source_store_code", "TEXT")
        _ensure_column(conn, "stock_ledger", "repair_batch_id", "TEXT")
        _ensure_column(conn, "stock_ledger", "supersedes_ledger_id", "INTEGER")

        # Normalize only rows that already have source-proven public articles.
        # Blank legacy rows remain blank and are not inferred by this migration.
        for table in ARTICLE_TABLES:
            conn.execute(
                f"""
                UPDATE {_quote(table)}
                SET line_identity_key = CASE
                    WHEN TRIM(COALESCE(source_entry_id, '')) <> ''
                        THEN 'ENTRY:' || TRIM(source_entry_id)
                    ELSE 'ARTICLE:' || UPPER(TRIM(kaspi_article))
                END
                WHERE (
                        TRIM(COALESCE(source_entry_id, '')) <> ''
                    AND TRIM(COALESCE(line_identity_key, '')) <>
                        'ENTRY:' || TRIM(source_entry_id)
                ) OR (
                        TRIM(COALESCE(source_entry_id, '')) = ''
                    AND TRIM(COALESCE(kaspi_article, '')) <> ''
                    AND TRIM(COALESCE(line_identity_key, '')) <>
                        'ARTICLE:' || UPPER(TRIM(kaspi_article))
                )
                """
            )

        for table, index_name in ARTICLE_INDEXES.items():
            _create_article_index(conn, table, index_name)
            _create_source_line_indexes(conn, table)

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_stock_ledger_order_line_identity
            ON stock_ledger (
                CAST(reference_id AS TEXT),
                UPPER(TRIM(COALESCE(source_store_code, store_code, ''))),
                UPPER(TRIM(COALESCE(line_identity_key, '')))
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_ledger_supersedes_ledger_id
            ON stock_ledger (supersedes_ledger_id)
            WHERE supersedes_ledger_id IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_ledger_source_identity (
                ledger_id INTEGER PRIMARY KEY
                    REFERENCES stock_ledger(ledger_id),
                source_entry_id TEXT NOT NULL UNIQUE,
                source_store_code TEXT NOT NULL,
                kaspi_article TEXT NOT NULL,
                line_identity_key TEXT NOT NULL,
                repair_batch_id TEXT NOT NULL,
                linked_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _print_errors(errors: Iterable[str]) -> None:
    for error in errors:
        print(f"  - {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persist stable public Kaspi article line identity"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply:
        errors = validate_public_article_line_grain(args.db)
        if errors:
            print("DRY RUN: public-article line-grain migration required:")
            _print_errors(errors)
        else:
            print("DRY RUN: public-article line-grain schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    errors = validate_public_article_line_grain(args.db)
    if errors:
        print("ERROR: public-article line-grain migration incomplete:")
        _print_errors(errors)
        return 1
    print("Public-article line-grain migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
