import sqlite3
from pathlib import Path

import scripts.generate_po_dashboard_data as dashboard


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            message_date TEXT,
            cargo_send_date TEXT,
            estimated_arrival_date TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO po_part (po_part_id, po_id, message_date, cargo_send_date, estimated_arrival_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("PO-5.2", "PO-5", "2026-01-21", "2026-01-31", "2026-02-21"),
            ("PO-4.1", "PO-4", "2025-12-21", "2026-01-21", "2026-02-11"),
            ("PO-6.0", "PO-6", "2026-02-04", "2026-02-07", "2026-02-28"),
            ("ARC-1.0", "PO_ARC-1", "2026-02-06", "2026-02-07", "2026-02-28"),
        ],
    )
    conn.commit()
    conn.close()


def test_archived_pos_sorted_by_cargo_send_date_ascending(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    archive_ids = dashboard.resolve_real_archive_ids(db_path=db_path)
    assert archive_ids == ["PO-4.1", "PO-5.2", "ARC-1.0", "PO-6.0"]
