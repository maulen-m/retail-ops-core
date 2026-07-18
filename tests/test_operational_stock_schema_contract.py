from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.migrate_028_operational_stock_truth_p0_schema import migrate
from scripts.validate_operational_stock_schema import (
    REQUIRED_OPERATIONAL_TABLES,
    validate_operational_stock_schema,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_operational_stock_schema_fails_on_empty_runtime_db(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    sqlite3.connect(str(db_path)).close()

    errors = validate_operational_stock_schema(db_path)

    assert any("source_manifest" in err for err in errors)
    assert any("stock_anchor" in err for err in errors)
    assert any("order_status_event" in err for err in errors)


def test_operational_stock_schema_passes_after_p0_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(str(db_path)).close()

    migrate(db_path)

    assert validate_operational_stock_schema(db_path) == []


def test_operational_stock_schema_sources_define_required_runtime_tables() -> None:
    schema_source = (PROJECT_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    migration_source = (
        PROJECT_ROOT / "scripts" / "migrate_028_operational_stock_truth_p0_schema.py"
    ).read_text(encoding="utf-8")
    combined = f"{schema_source}\n{migration_source}"

    missing = [
        table
        for table in REQUIRED_OPERATIONAL_TABLES
        if f"CREATE TABLE IF NOT EXISTS {table}" not in combined
    ]

    assert missing == []


def test_source_line_rollout_flags_legacy_mutable_unique_constraints(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY,
                order_id TEXT,
                kaspi_offer_name TEXT,
                store_code TEXT,
                sku_id TEXT,
                UNIQUE(order_id, kaspi_offer_name, sku_id, store_code)
            )
            """
        )
        for table in ("fact_orders_kaspi", "sales_fact_v2", "fact_sales"):
            for column in ("source_entry_id", "kaspi_article", "line_identity_key"):
                if column not in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        for column in (
            "source_entry_id",
            "kaspi_article",
            "line_identity_key",
            "source_store_code",
            "repair_batch_id",
            "supersedes_ledger_id",
        ):
            if column not in {row[1] for row in conn.execute("PRAGMA table_info(stock_ledger)")}:
                conn.execute(f"ALTER TABLE stock_ledger ADD COLUMN {column} TEXT")
        conn.execute(
            """
            CREATE TABLE stock_ledger_source_identity (
                ledger_id INTEGER PRIMARY KEY,
                source_entry_id TEXT,
                source_store_code TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT,
                repair_batch_id TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    errors = validate_operational_stock_schema(
        db_path,
        require_source_line_grain=True,
    )

    assert any("Legacy mutable UNIQUE constraint remains on sales_fact_v2" in e for e in errors)
    assert any("Legacy mutable UNIQUE constraint remains on fact_sales" in e for e in errors)
