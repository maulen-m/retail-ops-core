import sqlite3
from pathlib import Path

from scripts.migrate_022_po_execution_tables import migrate
from scripts.validate_schema import validate_schema


def test_validate_schema_fails_on_missing_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(str(db_path)).close()

    errors = validate_schema(db_path)
    assert any("fact_po_draft" in err for err in errors)


def test_validate_schema_fails_on_missing_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE fact_po_draft (draft_id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute(
        """
        CREATE TABLE fact_po_draft_lines (
            line_id INTEGER PRIMARY KEY,
            draft_id INTEGER,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            unit_cost_cny REAL,
            roic_pct REAL
        )
        """
    )
    conn.execute("CREATE TABLE fact_po_approvals (approval_id INTEGER PRIMARY KEY, draft_id INTEGER, decision TEXT)")
    conn.execute("CREATE TABLE fact_po_execution (execution_id INTEGER PRIMARY KEY, draft_id INTEGER, status TEXT)")
    conn.commit()
    conn.close()

    errors = validate_schema(db_path)
    assert any("missing columns" in err for err in errors)


def test_validate_schema_passes_after_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)

    errors = validate_schema(db_path)
    assert errors == []
