from __future__ import annotations

import sqlite3

import pytest

from core.db.sales_public_line_write_guard import (
    SalesPublicLineWriteGuardError,
    assert_legacy_writer_allowed,
    migrated_source_line_tables,
)


def test_guard_allows_legacy_schema_before_lineage_migration() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sales_fact_v2 (order_id TEXT, sku_id TEXT)")

    assert migrated_source_line_tables(conn, ("sales_fact_v2",)) == []
    assert_legacy_writer_allowed(
        conn,
        writer="legacy-test-writer",
        tables=("sales_fact_v2",),
    )


def test_guard_blocks_mutable_key_writer_after_lineage_migration() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            source_entry_id TEXT,
            kaspi_article TEXT,
            line_identity_key TEXT
        )
        """
    )

    assert migrated_source_line_tables(conn, ("missing", "sales_fact_v2")) == [
        "sales_fact_v2"
    ]
    with pytest.raises(
        SalesPublicLineWriteGuardError,
        match="not source-line-aware.*sales_fact_v2",
    ):
        assert_legacy_writer_allowed(
            conn,
            writer="legacy-test-writer",
            tables=("sales_fact_v2",),
        )
