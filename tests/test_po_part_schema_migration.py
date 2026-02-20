import sqlite3
from pathlib import Path

from scripts.migrate_023_po_parts_schema import migrate, validate_po_part_schema


def _create_minimal_po_tables(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            unit_cost_cny REAL NOT NULL,
            status TEXT DEFAULT 'PENDING'
        )
        """
    )
    conn.commit()
    conn.close()


def test_schema_validation_fails_before_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_minimal_po_tables(db_path)

    errors = validate_po_part_schema(db_path)
    assert any("po_part" in err for err in errors)
    assert any("po_line.po_part_id" in err for err in errors)


def test_schema_validation_passes_after_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_minimal_po_tables(db_path)

    migrate(db_path)
    errors = validate_po_part_schema(db_path)
    assert errors == []


def test_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_minimal_po_tables(db_path)

    migrate(db_path)
    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(po_line)").fetchall()}
    conn.close()

    assert "idx_po_line_part" in indexes
