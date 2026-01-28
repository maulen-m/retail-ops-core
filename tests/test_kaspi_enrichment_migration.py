import sqlite3
from pathlib import Path

from scripts.migrate_019_kaspi_enrichment import migrate


def test_migration_creates_enrichment_tables(tmp_path):
    db_path = tmp_path / "enrichment.db"
    sqlite3.connect(str(db_path)).close()

    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "fact_order_entries_kaspi" in tables
    assert "dim_point_of_service" in tables
    assert "dim_masterproduct" in tables
    assert "dim_merchantproduct" in tables
