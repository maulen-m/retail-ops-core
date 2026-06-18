"""
Tests for inventory snapshot ingestion.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest_inventory_snapshot import parse_inventory_excel, save_snapshot
from core.db import get_db

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
REQUIRES_DB = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="db/app.db missing; integration checks require seeded DB",
)


class TestParseInventoryExcel:
    """Tests for Excel parsing."""

    def test_parse_inventory_excel_returns_list(self):
        """Parse returns a list of dicts."""
        filepath = "excel/Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
        if not os.path.exists(filepath):
            pytest.skip("Inventory file not found")

        records = parse_inventory_excel(filepath)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_parse_inventory_excel_has_required_keys(self):
        """Each record has required keys."""
        filepath = "excel/Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
        if not os.path.exists(filepath):
            pytest.skip("Inventory file not found")

        records = parse_inventory_excel(filepath)
        required_keys = {"sku_id", "sku_key", "my_size", "current_stock"}

        for record in records[:5]:  # Check first 5
            assert required_keys <= set(record.keys())

    def test_parse_inventory_excel_stock_is_int(self):
        """current_stock should be integer."""
        filepath = "excel/Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
        if not os.path.exists(filepath):
            pytest.skip("Inventory file not found")

        records = parse_inventory_excel(filepath)

        for record in records:
            assert isinstance(record["current_stock"], int)


class TestSaveSnapshot:
    """Tests for saving snapshot to DB."""

    def test_save_snapshot_dry_run(self, tmp_path):
        """Dry run returns stats without saving."""
        filepath = "excel/Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
        if not os.path.exists(filepath):
            pytest.skip("Inventory file not found")

        records = parse_inventory_excel(filepath)

        with get_db(tmp_path / "inventory_snapshot.db") as conn:
            stats = save_snapshot(conn, records, "2099-01-01", dry_run=True)

        assert stats["size_records"] == len(records)
        assert stats["style_records"] > 0
        assert stats["total_units"] >= 0

    def test_save_snapshot_idempotent(self, tmp_path):
        """Running twice with same date should be idempotent."""
        filepath = "excel/Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
        if not os.path.exists(filepath):
            pytest.skip("Inventory file not found")

        records = parse_inventory_excel(filepath)
        test_date = "2099-12-31"

        with get_db(tmp_path / "inventory_snapshot.db") as conn:
            # First run
            stats1 = save_snapshot(conn, records, test_date, dry_run=False)

            # Second run - should overwrite
            stats2 = save_snapshot(conn, records, test_date, dry_run=False)

            # Check only one set of records exists
            cursor = conn.execute(
                "SELECT COUNT(*) FROM fact_inventory_snapshot_size WHERE snapshot_date = ?",
                (test_date,)
            )
            count = cursor.fetchone()[0]

            # Cleanup
            conn.execute(
                "DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = ?",
                (test_date,)
            )
            conn.commit()

        assert stats1["size_records"] == stats2["size_records"]
        assert count == len(records)


class TestInventoryIntegration:
    """Integration tests."""

    @REQUIRES_DB
    def test_inventory_loaded_correctly(self):
        """Verify Dec 6 inventory is in DB."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(current_stock) FROM fact_inventory_snapshot_size WHERE snapshot_date = '2025-12-06'"
            )
            count, total = cursor.fetchone()

        assert count == 221, f"Expected 221 records, got {count}"
        assert total == 5175, f"Expected 5175 total units, got {total}"
