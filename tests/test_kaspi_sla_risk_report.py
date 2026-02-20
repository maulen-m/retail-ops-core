import sqlite3
from pathlib import Path

from scripts.report_kaspi_sla_risk import build_sla_risk_report


def _init_orders_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                planned_shipment_date TEXT,
                actual_shipment_date TEXT,
                courier_transmission_planning_date TEXT,
                courier_transmission_date TEXT,
                returned_to_warehouse INTEGER,
                express INTEGER,
                signature_required INTEGER
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_kaspi_sla_risk_report(tmp_path):
    db_path = tmp_path / "sla.db"
    _init_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, planned_shipment_date, actual_shipment_date,
                courier_transmission_planning_date, courier_transmission_date,
                returned_to_warehouse, express, signature_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD1",
                "STOREB",
                "2026-01-10",
                "2026-01-12",
                "2026-01-10",
                "2026-01-11",
                1,
                1,
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, planned_shipment_date, actual_shipment_date,
                courier_transmission_planning_date, courier_transmission_date,
                returned_to_warehouse, express, signature_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD2",
                "STOREB",
                "2026-01-10",
                "2026-01-10",
                None,
                None,
                0,
                0,
                1,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    out_path = tmp_path / "sla_report.md"
    build_sla_risk_report(db_path=db_path, output_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    assert "total_orders: 2" in content
    assert "avg_ship_delay_days: 1.0" in content
    assert "avg_transmission_delay_days: 1.0" in content
    assert "returned_to_warehouse: 1" in content
    assert "express: 1" in content
    assert "signature_required: 1" in content
