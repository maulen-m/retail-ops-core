import sqlite3
from pathlib import Path

from scripts.migrate_024_order_synced_at import validate_synced_at_schema, migrate


def _create_orders_table(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            store_code TEXT,
            status_updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def test_validate_synced_at_schema_fails_before_migration(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_orders_table(db)
    errors = validate_synced_at_schema(db)
    assert any("synced_at" in err for err in errors)


def test_migrate_adds_synced_at_column_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_orders_table(db)

    migrate(db)
    migrate(db)

    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
    conn.close()
    assert "synced_at" in cols
    assert not validate_synced_at_schema(db)
