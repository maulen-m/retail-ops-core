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
