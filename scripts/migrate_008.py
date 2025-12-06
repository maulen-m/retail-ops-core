#!/usr/bin/env python3
"""
Apply migration 008: Capital allocation tables.

Run: python scripts/migrate_008.py

TASK-074
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
MIGRATION_FILE = Path(__file__).parent.parent / "db" / "migrations" / "008_capital_allocation.sql"


def migrate():
    conn = sqlite3.connect(DB_PATH)

    # Read and execute migration SQL
    with open(MIGRATION_FILE) as f:
        sql = f.read()

    conn.executescript(sql)
    conn.commit()
    conn.close()

    print("✓ Migration 008 applied: fact_capital_allocation, fact_portfolio_summary")


if __name__ == "__main__":
    migrate()
