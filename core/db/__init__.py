"""
Database connection helper for Project 3.
Clean, no globals, dependency-injectable.

Moved to core/db/__init__.py to allow for submodules like queries.py.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

# Default DB path (can be overridden)
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a new database connection with proper settings."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row  # Access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(db_path: Optional[Path] = None):
    """Context manager for database connections.

    Usage:
        with get_db() as conn:
            cursor = conn.execute("SELECT * FROM dim_store")
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(
    db_path: Optional[Path] = None, schema_path: Optional[Path] = None
):
    """Initialize database from schema.sql.

    Args:
        db_path: Path to SQLite database file
        schema_path: Path to schema.sql file

    Returns:
        True if successful
    """
    db = db_path or DEFAULT_DB_PATH
    schema = schema_path or (
        Path(__file__).parent.parent.parent / "db" / "schema.sql"
    )

    if not schema.exists():
        raise FileNotFoundError(f"Schema not found: {schema}")

    # Ensure db directory exists
    db.parent.mkdir(parents=True, exist_ok=True)

    with get_db(db) as conn:
        with open(schema, 'r') as f:
            conn.executescript(f.read())

    return True


# Export submodules
from . import queries
from . import ledger


if __name__ == "__main__":
    # Quick test
    print(f"DB path: {DEFAULT_DB_PATH}")
    init_db()
    print("Database initialized successfully!")
