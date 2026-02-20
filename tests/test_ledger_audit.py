"""
Targeted tests for log_audit in core/db/ledger.py.
"""

import sqlite3
from pathlib import Path
import tempfile
import os

from core.db.ledger import log_audit


def test_log_audit_inserts_row():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE fact_input_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            change_type TEXT NOT NULL,
            source TEXT DEFAULT 'SYSTEM'
        )
    """)
    conn.commit()
    conn.close()

    audit_id = log_audit(
        table_name="sales_fact_v2",
        record_id="import_001",
        field_name="*",
        old_value=None,
        new_value="1 row",
        change_type="INSERT",
        reason="Batch import",
        source="IMPORT",
        db_path=db_path,
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM fact_input_audit WHERE audit_id = ?",
        (audit_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["table_name"] == "sales_fact_v2"
    assert row["record_id"] == "import_001"
    assert row["field_name"] == "*"
    assert row["new_value"] == "1 row"
    assert row["change_type"] == "INSERT"
    assert row["source"] == "IMPORT"

    if db_path.exists():
        db_path.unlink()
