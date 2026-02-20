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
        cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(fact_order_entries_kaspi)").fetchall()
        ]
    finally:
        conn.close()

    assert "fact_order_entries_kaspi" in tables
    assert "dim_point_of_service" in tables
    assert "dim_masterproduct" in tables
    assert "dim_merchantproduct" in tables

    for required in (
        "unit_type",
        "min_allowed_weight",
        "weight_kg",
        "entry_number",
        "category_code",
        "category_title",
        "delivery_cost_kzt",
        "base_price_kzt",
        "point_of_service_id",
        "delivery_point_of_service_id",
    ):
        assert required in cols
