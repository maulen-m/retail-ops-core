import sqlite3
from pathlib import Path

import scripts.generate_po_dashboard_data as dashboard


def _seed_po_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            message_date TEXT,
            ship_date_seller TEXT,
            ship_date_cargo TEXT,
            status TEXT,
            weight_nom_kg REAL,
            total_places INTEGER
        );
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING'
        );
        """
    )
    conn.execute(
        """
        INSERT INTO po_header (
            po_id, message_date, ship_date_seller, ship_date_cargo, status, weight_nom_kg, total_places
        )
        VALUES ('PO-5', '2026-01-21', '2026-02-04', '2026-02-04', 'SHIPPED_CARGO', 0.0, 0)
        """
    )
    rows = [
        ("PO-5", None, "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_M", "M", 110, 0, "IN_TRANSIT"),
        ("PO-5", None, "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_L", "L", 240, 0, "IN_TRANSIT"),
        ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_M", "M", 110, 0, "IN_TRANSIT"),
        ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_L", "L", 240, 0, "IN_TRANSIT"),
    ]
    conn.executemany(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_load_po_orders_prefers_part_rows_over_legacy_null_part(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    monkeypatch.setattr(dashboard, "DB_PATH", db_path)

    po = dashboard.load_po_orders("PO-5", db_path=db_path)
    assert po is not None
    sku_orders = po["orders_by_sku"]["CL_NEW-CLO2_MEN_SUIT-61_BLACK"]
    assert sku_orders["M"] == 110
    assert sku_orders["L"] == 240
    assert sum(sku_orders.values()) == 350


def test_open_inbound_by_size_prefers_part_rows(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    monkeypatch.setattr(dashboard, "DB_PATH", db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        inbound = dashboard._load_open_inbound_by_size_from_po(conn, "CL_NEW-CLO2_MEN_SUIT-61_BLACK")
    assert inbound == {"M": 110, "L": 240}
