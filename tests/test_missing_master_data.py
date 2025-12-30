"""
Tests for Part 6: Missing Master Data Report

Tests the detection and reporting of SKUs with missing:
- Weight
- Cost
- Price
- Supplier mapping
"""

import pytest
import sqlite3
from datetime import date
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.report_missing_master_data import (
    get_missing_master_data,
    write_report_csv,
    format_telegram_summary,
    get_top_missing_data_blockers,
    MissingDataReport,
    MissingDataSKU,
)


@pytest.fixture
def test_db(tmp_path):
    """Create test database with SKUs having various missing data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            sku_id TEXT,
            model TEXT,
            active_flag INTEGER DEFAULT 1,
            weight_kg REAL,
            base_cost_cny REAL,
            cogs_kzt REAL,
            kaspi_price_kzt REAL,
            supplier_code TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE fact_demand_estimates (
            sku_key TEXT PRIMARY KEY,
            d_final REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE fact_sku_metrics (
            sku_key TEXT PRIMARY KEY,
            d30 REAL
        )
    """)

    # Insert test SKUs
    # Complete SKU - no missing data
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_COMPLETE', 'SKU_COMPLETE_M', 'Complete Product', 1, 0.5, 100, 10000, 15000, 'SUPPLIER_A')
    """)

    # Missing weight only
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_NO_WEIGHT', 'SKU_NO_WEIGHT_M', 'No Weight', 1, NULL, 100, 10000, 15000, 'SUPPLIER_A')
    """)

    # Missing cost
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_NO_COST', 'SKU_NO_COST_M', 'No Cost', 1, 0.5, NULL, NULL, 15000, 'SUPPLIER_A')
    """)

    # Missing price
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_NO_PRICE', 'SKU_NO_PRICE_M', 'No Price', 1, 0.5, 100, 10000, NULL, 'SUPPLIER_A')
    """)

    # Missing supplier
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_NO_SUPPLIER', 'SKU_NO_SUPPLIER_M', 'No Supplier', 1, 0.5, 100, 10000, 15000, NULL)
    """)

    # Missing multiple fields
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_MISSING_ALL', 'SKU_MISSING_ALL_M', 'Missing All', 1, NULL, NULL, NULL, NULL, NULL)
    """)

    # Inactive SKU (should be ignored)
    cursor.execute("""
        INSERT INTO dim_sku VALUES
        ('SKU_INACTIVE', 'SKU_INACTIVE_M', 'Inactive', 0, NULL, NULL, NULL, NULL, NULL)
    """)

    # Add demand estimates for spend calculation
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_NO_WEIGHT', 5.0)")
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_NO_COST', 3.0)")
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_MISSING_ALL', 10.0)")

    conn.commit()
    conn.close()

    return db_path


class TestMissingDataDetection:
    """Test detection of missing master data."""

    def test_detects_missing_weight(self, test_db):
        """Verify missing weight is detected."""
        report = get_missing_master_data(test_db)

        # SKU_NO_WEIGHT and SKU_MISSING_ALL have no weight
        assert report.missing_weight >= 2

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_NO_WEIGHT"), None)
        assert sku is not None
        assert 'weight' in sku.missing_fields

    def test_detects_missing_cost(self, test_db):
        """Verify missing cost is detected."""
        report = get_missing_master_data(test_db)

        assert report.missing_cost >= 2

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_NO_COST"), None)
        assert sku is not None
        assert 'cost' in sku.missing_fields

    def test_detects_missing_price(self, test_db):
        """Verify missing price is detected."""
        report = get_missing_master_data(test_db)

        assert report.missing_price >= 2

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_NO_PRICE"), None)
        assert sku is not None
        assert 'price' in sku.missing_fields

    def test_detects_missing_supplier(self, test_db):
        """Verify missing supplier is detected."""
        report = get_missing_master_data(test_db)

        assert report.missing_supplier >= 2

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_NO_SUPPLIER"), None)
        assert sku is not None
        assert 'supplier' in sku.missing_fields

    def test_detects_multiple_missing_fields(self, test_db):
        """Verify multiple missing fields are detected on same SKU."""
        report = get_missing_master_data(test_db)

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_MISSING_ALL"), None)
        assert sku is not None
        assert len(sku.missing_fields) >= 4
        assert 'weight' in sku.missing_fields
        assert 'cost' in sku.missing_fields
        assert 'price' in sku.missing_fields
        assert 'supplier' in sku.missing_fields

    def test_complete_sku_not_included(self, test_db):
        """Verify SKU with all data is not in report."""
        report = get_missing_master_data(test_db)

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_COMPLETE"), None)
        assert sku is None

    def test_inactive_sku_ignored(self, test_db):
        """Verify inactive SKUs are ignored."""
        report = get_missing_master_data(test_db)

        sku = next((s for s in report.sku_details if s.sku_key == "SKU_INACTIVE"), None)
        assert sku is None


class TestSpendPrioritization:
    """Test prioritization by spend impact."""

    def test_sorted_by_spend_descending(self, test_db):
        """Verify results are sorted by proposed spend descending."""
        report = get_missing_master_data(test_db)

        for i in range(len(report.sku_details) - 1):
            assert report.sku_details[i].proposed_spend_kzt >= report.sku_details[i + 1].proposed_spend_kzt

    def test_spend_calculated_from_demand_and_cost(self, test_db):
        """Verify spend is calculated using demand and cost."""
        report = get_missing_master_data(test_db)

        # SKU_NO_WEIGHT: demand=5, cogs=10000, spend = 5*30*10000 = 1,500,000
        sku = next((s for s in report.sku_details if s.sku_key == "SKU_NO_WEIGHT"), None)
        assert sku is not None
        assert sku.proposed_spend_kzt == 5 * 30 * 10000


class TestFieldFilter:
    """Test field filter functionality."""

    def test_filter_by_weight(self, test_db):
        """Verify filter returns only weight-missing SKUs."""
        report = get_missing_master_data(test_db, field_filter="weight")

        for sku in report.sku_details:
            assert 'weight' in sku.missing_fields

    def test_filter_by_cost(self, test_db):
        """Verify filter returns only cost-missing SKUs."""
        report = get_missing_master_data(test_db, field_filter="cost")

        for sku in report.sku_details:
            assert 'cost' in sku.missing_fields

    def test_filter_by_supplier(self, test_db):
        """Verify filter returns only supplier-missing SKUs."""
        report = get_missing_master_data(test_db, field_filter="supplier")

        for sku in report.sku_details:
            assert 'supplier' in sku.missing_fields


class TestReportOutput:
    """Test report CSV and Telegram output."""

    def test_write_csv(self, test_db, tmp_path):
        """Verify CSV report is created correctly."""
        report = get_missing_master_data(test_db)
        output_path = write_report_csv(report, tmp_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Check sections
        assert "MISSING MASTER DATA REPORT" in content
        assert "SUMMARY" in content
        assert "MISSING BY FIELD" in content
        assert "SKU DETAILS" in content

        # Check data
        assert "SKU_NO_WEIGHT" in content
        assert "weight" in content

    def test_telegram_summary_format(self, test_db):
        """Verify Telegram summary is formatted correctly."""
        report = get_missing_master_data(test_db)
        summary = format_telegram_summary(report)

        assert "<b>Missing Master Data Report</b>" in summary
        assert "Summary:" in summary
        assert "Missing by Field:" in summary
        assert "Top" in summary

    def test_get_top_blockers(self, test_db):
        """Verify get_top_missing_data_blockers returns correct format."""
        blockers = get_top_missing_data_blockers(test_db, limit=3)

        assert len(blockers) <= 3
        for blocker in blockers:
            assert "sku_key" in blocker
            assert "blocked_spend_kzt" in blocker
            assert "missing_fields" in blocker


class TestSummaryStats:
    """Test summary statistics calculation."""

    def test_total_skus_counted(self, test_db):
        """Verify total SKUs includes all active SKUs."""
        report = get_missing_master_data(test_db)

        # 6 active SKUs (SKU_INACTIVE excluded)
        assert report.total_skus_checked == 6

    def test_blocked_spend_totaled(self, test_db):
        """Verify total blocked spend is summed correctly."""
        report = get_missing_master_data(test_db)

        expected = sum(s.proposed_spend_kzt for s in report.sku_details)
        assert report.total_blocked_spend_kzt == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
