from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from core.sales.publication_prerequisites import (
    MinimalPublicationSchemaError,
    build_minimal_publication_schema_contract,
    install_minimal_publication_schema,
    require_matching_minimal_publication_schema,
    require_minimal_publication_schema,
)


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                kaspi_article TEXT, line_identity_key TEXT
            );
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT
            );
            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT
            );
            INSERT INTO fact_orders_kaspi VALUES (1, 'O1', 'ACMEWEAR', 'A1', 'L1');
            INSERT INTO sales_fact_v2 VALUES (1, 'O1', 'ACMEWEAR');
            INSERT INTO fact_sales VALUES (1, 'O1', 'ACMEWEAR');
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_contract_requires_exact_seven_columns_and_three_indexes(
    tmp_path: Path,
) -> None:
    db = tmp_path / "contract.db"
    _seed(db)
    conn = sqlite3.connect(db)
    try:
        legacy = build_minimal_publication_schema_contract(conn)
        with pytest.raises(MinimalPublicationSchemaError, match="not exact"):
            require_minimal_publication_schema(legacy)

        install_minimal_publication_schema(conn)
        conn.commit()
        current = build_minimal_publication_schema_contract(conn)
        require_minimal_publication_schema(current)
        assert current["required_column_count"] == 7
        assert current["required_index_count"] == 3
        assert current["errors"] == []
    finally:
        conn.close()


def test_matching_contract_rejects_rehashed_tamper(tmp_path: Path) -> None:
    db = tmp_path / "tamper.db"
    _seed(db)
    conn = sqlite3.connect(db)
    try:
        install_minimal_publication_schema(conn)
        conn.commit()
        current = build_minimal_publication_schema_contract(conn)
        tampered = copy.deepcopy(current)
        tampered["required_column_count"] = 8
        # A changed body with the old hash must fail immediately.
        with pytest.raises(MinimalPublicationSchemaError, match="hash mismatch"):
            require_matching_minimal_publication_schema(
                conn,
                pinned_contract=tampered,
            )
    finally:
        conn.close()


def test_duplicate_nonblank_entry_blocks_index_install(tmp_path: Path) -> None:
    db = tmp_path / "duplicate.db"
    _seed(db)
    conn = sqlite3.connect(db)
    try:
        for table in ("fact_orders_kaspi", "sales_fact_v2", "fact_sales"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN source_entry_id TEXT")
        for table in ("sales_fact_v2", "fact_sales"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN kaspi_article TEXT")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN line_identity_key TEXT")
        conn.execute("UPDATE sales_fact_v2 SET source_entry_id='DUP' WHERE sale_id=1")
        conn.execute(
            "INSERT INTO sales_fact_v2(sale_id,order_id,store_code,source_entry_id) "
            "VALUES (2,'O2','ACMEWEAR','DUP')"
        )
        with pytest.raises(MinimalPublicationSchemaError, match="duplicate"):
            install_minimal_publication_schema(conn)
    finally:
        conn.rollback()
        conn.close()
