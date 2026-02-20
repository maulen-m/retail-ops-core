"""
Tests for StockTimelineBuilder arrival aggregation with estimated arrivals.
"""

import sqlite3
import tempfile
from pathlib import Path

from core.calc.stock_timeline import StockTimelineBuilder


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE fact_po_lines (
            sku_id TEXT,
            est_arrival_date TEXT,
            actual_arrival_date TEXT,
            order_quantity INTEGER,
            received_qty INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()


def test_arrivals_include_estimated_in_transit():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO fact_po_lines VALUES (?, ?, ?, ?, ?, ?)",
        ("SKU1", None, "2026-01-10", 5, 5, "DELIVERED"),
    )
    conn.execute(
        "INSERT INTO fact_po_lines VALUES (?, ?, ?, ?, ?, ?)",
        ("SKU1", "2026-01-12", None, 10, 2, "IN_TRANSIT"),
    )
    conn.execute(
        "INSERT INTO fact_po_lines VALUES (?, ?, ?, ?, ?, ?)",
        ("SKU1", "2026-01-12", None, 3, 0, "UNPAID"),
    )
    conn.commit()
    conn.close()

    builder = StockTimelineBuilder(db_path)
    arrivals = builder.get_arrivals_by_sku_id(
        "2026-01-09",
        "2026-01-12",
        include_estimated=True,
    )
    builder.close()

    assert arrivals["SKU1"]["2026-01-10"] == 5
    assert arrivals["SKU1"]["2026-01-12"] == 8

    db_path.unlink(missing_ok=True)
