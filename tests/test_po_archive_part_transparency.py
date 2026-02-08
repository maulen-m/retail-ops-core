import sqlite3
from pathlib import Path

import scripts.generate_po_dashboard_data as dashboard


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT,
            status TEXT,
            message_date TEXT,
            ship_date_seller TEXT,
            ship_date_cargo TEXT,
            alm_arrival_nom TEXT,
            ast_arrival_nom TEXT,
            alm_arrival_real TEXT,
            ast_arrival_real TEXT,
            units_total INTEGER,
            units_received INTEGER,
            weight_nom_kg REAL,
            weight_real_kg REAL,
            total_places INTEGER,
            total_cost_cny REAL,
            total_cost_kzt_supplier REAL,
            total_landed_cost_kzt REAL,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            supplier_id TEXT,
            message_date TEXT,
            cargo_send_date TEXT,
            estimated_arrival_date TEXT,
            actual_arrival_date TEXT,
            status TEXT,
            total_units INTEGER,
            est_weight_kg REAL,
            total_bags INTEGER
        );
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER
        );
        """
    )

    conn.executemany(
        """
        INSERT INTO po_header (
            po_id, supplier_code, status, message_date, ship_date_cargo,
            ast_arrival_nom, ast_arrival_real, units_total, units_received,
            weight_nom_kg, total_places, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        [
            ("PO-5", "SHR", "IN_TRANSIT", "2026-01-21", "2026-01-30", "2026-02-20", None, 4800, 0, 2647.5, 63),
            ("PO-6", "SHR", "IN_TRANSIT", "2026-02-04", "2026-02-07", "2026-02-28", None, 1710, 0, 0.0, 0),
            ("PO_ARC-1", "ARC", "IN_TRANSIT", "2026-02-06", "2026-02-07", "2026-02-28", None, 265, 0, 0.0, 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO po_part (
            po_part_id, po_id, supplier_id, message_date, cargo_send_date,
            estimated_arrival_date, actual_arrival_date, status, total_units, est_weight_kg, total_bags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("PO-5.1", "PO-5", "SHR", "2026-01-21", "2026-01-30", "2026-02-20", None, "IN_TRANSIT", 820, 516.6, 10),
            ("PO-5.2", "PO-5", "SHR", "2026-01-21", "2026-01-30", "2026-02-20", None, "IN_TRANSIT", 3980, 2188.5, 53),
            ("PO-6.0", "PO-6", "SHR", "2026-02-04", "2026-02-07", "2026-02-28", None, "IN_TRANSIT", 1710, 326.6, 11),
            ("ARC-1.0", "PO_ARC-1", "ARC", "2026-02-06", "2026-02-07", "2026-02-28", None, "IN_TRANSIT", 265, 172.25, 4),
            ("TOTAL", "nan", "", None, None, None, None, "NAN", 0, 0.0, 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("PO-5", "PO-5.1", "CL_OC_MEN_LINE51_WHITE", "CL_OC_MEN_LINE51_WHITE_M", "M", 85, 0),
            ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_M", "M", 110, 0),
            ("PO-6", "PO-6.0", "Bag_gift", "Bag_gift_ONE_SIZE", "ONE_SIZE", 1000, 0),
            ("PO-6", "PO-6.0", "CL_NC_MEN_RUSH-31_BLACK", "CL_NC_MEN_RUSH-31_BLACK_M", "M", 30, 0),
        ],
    )
    conn.commit()
    conn.close()


def test_resolve_real_archive_ids_prefers_part_ids_and_filters_summary_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    archive_ids = dashboard.resolve_real_archive_ids(db_path=db_path)

    assert "PO-5.1" in archive_ids
    assert "PO-5.2" in archive_ids
    assert "PO-6.0" in archive_ids
    assert "ARC-1.0" in archive_ids
    assert "TOTAL" not in archive_ids


def test_load_real_pos_uses_part_grain_with_weight_and_bags(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    rows = dashboard.load_real_pos(db_path=db_path)
    ids = {row["po_id"] for row in rows}

    assert "PO-6.0" in ids
    assert "ARC-1.0" in ids
    po6 = [row for row in rows if row["po_id"] == "PO-6.0"][0]
    assert po6["units_total"] == 1710
    assert float(po6["weight_nom_kg"] or 0.0) == 326.6
    assert int(po6["total_places"] or 0) == 11


def test_load_po_part_orders_returns_part_specific_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    po = dashboard.load_po_part_orders("PO-5.2", db_path=db_path)

    assert po is not None
    assert po["po_id"] == "PO-5"
    assert po["po_part_id"] == "PO-5.2"
    assert po["orders_by_sku"]["CL_NEW-CLO2_MEN_SUIT-61_BLACK"]["M"] == 110


def test_load_real_pos_keeps_older_received_part_ids_for_transparency(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO po_part (
            po_part_id, po_id, supplier_id, message_date, cargo_send_date,
            estimated_arrival_date, actual_arrival_date, status, total_units, est_weight_kg, total_bags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PO-4.0",
            "PO-4",
            "SHR",
            "2025-12-01",
            "2025-12-08",
            "2025-12-25",
            "2025-12-24",
            "RECEIVED",
            1810,
            520.5,
            14,
        ),
    )
    conn.execute(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("PO-4", "PO-4.0", "CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE52_BLACK_L", "L", 100, 100),
    )
    conn.commit()
    conn.close()

    rows = dashboard.load_real_pos(db_path=db_path)
    ids = {row["po_id"] for row in rows}
    assert "PO-4.0" in ids
