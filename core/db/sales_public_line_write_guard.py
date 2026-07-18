"""Fail-closed guard for legacy writers after stable sales-line migration.

Writers that key rows by mutable SKU, size, display name, or snapshot date must
not rewrite tables once entry/article lineage columns are present. They must be
upgraded and independently tested before this guard is removed for that writer.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable


SOURCE_LINE_COLUMNS = {"source_entry_id", "kaspi_article", "line_identity_key"}


class SalesPublicLineWriteGuardError(RuntimeError):
    """Raised when a legacy writer could erase or duplicate stable line truth."""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def migrated_source_line_tables(
    conn: sqlite3.Connection,
    tables: Iterable[str],
) -> list[str]:
    return sorted(
        table
        for table in tables
        if SOURCE_LINE_COLUMNS.issubset(_columns(conn, table))
    )


def assert_legacy_writer_allowed(
    conn: sqlite3.Connection,
    *,
    writer: str,
    tables: Iterable[str],
) -> None:
    migrated = migrated_source_line_tables(conn, tables)
    if migrated:
        raise SalesPublicLineWriteGuardError(
            f"{writer} is not source-line-aware and is blocked because stable "
            f"entry/article lineage is installed on: {', '.join(migrated)}. "
            "Use an entry-first writer that persists source_entry_id, "
            "kaspi_article, and line_identity_key and has a dedicated regression "
            "for distinct immutable entries sharing mutable SKU/display fields."
        )
