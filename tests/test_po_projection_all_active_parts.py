import sqlite3
from datetime import date
from pathlib import Path

import scripts.generate_po_dashboard_data as dashboard


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            estimated_arrival_date TEXT,
            status TEXT
        );
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            order_qty INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO po_part (po_part_id, po_id, estimated_arrival_date, status)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("PO-5.1", "PO-5", "2026-02-20", "IN_TRANSIT"),
            ("PO-5.2", "PO-5", "2026-02-21", "IN_TRANSIT"),
            ("PO-4.1", "PO-4", "2026-02-05", "RECEIVED"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, my_size, order_qty)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("PO-5", "PO-5.1", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 120),
            ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 220),
            ("PO-4", "PO-4.1", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 300),
        ],
    )
    conn.commit()
    conn.close()


def test_projection_uses_all_in_transit_po_parts_not_single_latest_po(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    orders = dashboard.load_active_part_orders_for_projection(db_path=db_path)
    assert "CL_NEW-CLO2_MEN_SUIT-61_BLACK" in orders
    sku_orders = sorted(orders["CL_NEW-CLO2_MEN_SUIT-61_BLACK"], key=lambda item: item[0])
    assert len(sku_orders) == 2
    assert sku_orders[0][0] == date(2026, 2, 20)
    assert sku_orders[1][0] == date(2026, 2, 21)
    assert sku_orders[0][2]["M"] == 120
    assert sku_orders[1][2]["L"] == 220


def test_no_double_count_between_snapshot_inbound_and_active_part_arrivals(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    orders = dashboard.load_active_part_orders_for_projection(db_path=db_path)

    by_sku, by_size = dashboard.compute_existing_inbound_from_active_parts(orders)
    assert by_sku["CL_NEW-CLO2_MEN_SUIT-61_BLACK"] == 340
    assert by_size["CL_NEW-CLO2_MEN_SUIT-61_BLACK"]["M"] == 120
    assert by_size["CL_NEW-CLO2_MEN_SUIT-61_BLACK"]["L"] == 220
