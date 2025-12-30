"""
Tests for Part 6: Weekly Autonomy KPI Report

Tests the weekly report generation including:
- Forecast bias calculation
- OOS metrics
- Inventory turns
- Blocked spend aggregation
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_weekly_autonomy_report import (
    get_forecast_bias,
    get_oos_metrics,
    get_inventory_turns,
    get_blocked_spend_by_reason,
    generate_weekly_report,
    write_report_csv,
    format_telegram_summary,
    WeeklyReport,
    SKUBias,
    OOSMetric,
    InventoryTurn,
)


@pytest.fixture
def test_db(tmp_path):
    """Create test database with required tables and sample data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create required tables
    cursor.execute("""
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER DEFAULT 1,
            kaspi_price_kzt REAL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE fact_sales_daily (
            sku_key TEXT,
            sale_date TEXT,
            quantity INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE fact_sales (
            sku_key TEXT,
            order_date TEXT,
            quantity INTEGER,
            unit_price REAL
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

    cursor.execute("""
        CREATE TABLE fact_inventory_snapshot_size (
            sku_key TEXT,
            snapshot_date TEXT,
            current_stock INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE fact_run_steps (
            step_id INTEGER PRIMARY KEY,
            run_id INTEGER,
            step_name TEXT,
            output_file TEXT,
            started_at TEXT
        )
    """)

    # Insert test data
    today = date.today()
    week_ago = today - timedelta(days=6)

    # SKUs
    cursor.execute("INSERT INTO dim_sku VALUES ('SKU_A', 1, 10000)")
    cursor.execute("INSERT INTO dim_sku VALUES ('SKU_B', 1, 15000)")
    cursor.execute("INSERT INTO dim_sku VALUES ('SKU_C', 1, 20000)")

    # Demand forecasts
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_A', 5.0)")  # 5/day
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_B', 3.0)")  # 3/day
    cursor.execute("INSERT INTO fact_demand_estimates VALUES ('SKU_C', 10.0)")  # 10/day

    # Actual sales (for 7 days)
    for i in range(7):
        d = (week_ago + timedelta(days=i)).isoformat()
        cursor.execute("INSERT INTO fact_sales_daily VALUES ('SKU_A', ?, 6)", (d,))  # Under-forecast
        cursor.execute("INSERT INTO fact_sales_daily VALUES ('SKU_B', ?, 2)", (d,))  # Over-forecast
        cursor.execute("INSERT INTO fact_sales_daily VALUES ('SKU_C', ?, 10)", (d,))  # Accurate

        cursor.execute("INSERT INTO fact_sales VALUES ('SKU_A', ?, 6, 10000)", (d,))
        cursor.execute("INSERT INTO fact_sales VALUES ('SKU_B', ?, 2, 15000)", (d,))
        cursor.execute("INSERT INTO fact_sales VALUES ('SKU_C', ?, 10, 20000)", (d,))

    # Inventory snapshots (with OOS days)
    for i in range(7):
        d = (week_ago + timedelta(days=i)).isoformat()
        cursor.execute("INSERT INTO fact_inventory_snapshot_size VALUES ('SKU_A', ?, 50)", (d,))
        cursor.execute("INSERT INTO fact_inventory_snapshot_size VALUES ('SKU_B', ?, 30)", (d,))
        # SKU_C has OOS on 2 days
        if i < 2:
            cursor.execute("INSERT INTO fact_inventory_snapshot_size VALUES ('SKU_C', ?, 0)", (d,))
        else:
            cursor.execute("INSERT INTO fact_inventory_snapshot_size VALUES ('SKU_C', ?, 40)", (d,))

    conn.commit()
    conn.close()

    return db_path


class TestForecastBias:
    """Test forecast bias calculation."""

    def test_bias_calculation(self, test_db):
        """Verify bias is calculated correctly."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        biases = get_forecast_bias(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        assert len(biases) >= 3

        # Find each SKU
        sku_a = next((b for b in biases if b.sku_key == "SKU_A"), None)
        sku_b = next((b for b in biases if b.sku_key == "SKU_B"), None)
        sku_c = next((b for b in biases if b.sku_key == "SKU_C"), None)

        # SKU_A: forecast 35 (5*7), actual 42 (6*7) = -16.7% (under-forecast)
        assert sku_a is not None
        assert sku_a.bias_pct < 0
        assert sku_a.bias_direction == "UNDER"

        # SKU_B: forecast 21 (3*7), actual 14 (2*7) = +50% (over-forecast)
        assert sku_b is not None
        assert sku_b.bias_pct > 0
        assert sku_b.bias_direction == "OVER"

        # SKU_C: forecast 70, actual 70 = 0% (accurate)
        assert sku_c is not None
        assert abs(sku_c.bias_pct) <= 10
        assert sku_c.bias_direction == "ACCURATE"

    def test_sorted_by_absolute_bias(self, test_db):
        """Verify results are sorted by absolute bias."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        biases = get_forecast_bias(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        # Should be sorted by absolute bias descending
        for i in range(len(biases) - 1):
            assert abs(biases[i].bias_pct) >= abs(biases[i + 1].bias_pct)


class TestOOSMetrics:
    """Test OOS metrics calculation."""

    def test_oos_days_counted(self, test_db):
        """Verify OOS days are counted correctly."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        metrics = get_oos_metrics(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        # SKU_C has 2 OOS days
        sku_c = next((m for m in metrics if m.sku_key == "SKU_C"), None)
        assert sku_c is not None
        assert sku_c.oos_days == 2

    def test_lost_sales_estimated(self, test_db):
        """Verify lost sales proxy is calculated."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        metrics = get_oos_metrics(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        sku_c = next((m for m in metrics if m.sku_key == "SKU_C"), None)
        assert sku_c is not None

        # Lost sales = OOS days * daily demand = 2 * 10 = 20
        assert sku_c.estimated_lost_sales == 20

        # Lost revenue = lost sales * price = 20 * 20000 = 400000
        assert sku_c.estimated_lost_revenue_kzt == 400000


class TestInventoryTurns:
    """Test inventory turns calculation."""

    def test_turns_calculated(self, test_db):
        """Verify inventory turns are calculated."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        turns = get_inventory_turns(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        assert len(turns) >= 2

        # All should have positive turns
        for t in turns:
            assert t.turns_annualized > 0

    def test_higher_sales_higher_turns(self, test_db):
        """Verify SKU with higher sales has higher turns."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        turns = get_inventory_turns(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        sku_a = next((t for t in turns if t.sku_key == "SKU_A"), None)
        sku_b = next((t for t in turns if t.sku_key == "SKU_B"), None)

        assert sku_a is not None
        assert sku_b is not None

        # SKU_A has higher sales (42 vs 14), similar stock, so higher turns
        assert sku_a.turns_annualized > sku_b.turns_annualized


class TestWeeklyReport:
    """Test complete weekly report generation."""

    def test_report_generation(self, test_db):
        """Verify complete report is generated."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        report = generate_weekly_report(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        assert report.report_date == today.isoformat()
        assert report.start_date == week_ago.isoformat()
        assert report.end_date == today.isoformat()
        assert report.total_skus_analyzed > 0
        assert len(report.top_sku_biases) > 0
        assert len(report.oos_metrics) > 0
        assert len(report.inventory_turns) > 0

    def test_write_csv(self, test_db, tmp_path):
        """Verify CSV output is created correctly."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        report = generate_weekly_report(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        output_path = write_report_csv(report, tmp_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Check required sections
        assert "WEEKLY AUTONOMY KPI REPORT" in content
        assert "SUMMARY" in content
        assert "TOP SKUs BY FORECAST BIAS" in content
        assert "TOP SKUs BY LOST SALES" in content
        assert "TOP SKUs BY INVENTORY TURNS" in content

    def test_telegram_summary_format(self, test_db):
        """Verify Telegram summary is formatted correctly."""
        today = date.today()
        week_ago = today - timedelta(days=6)

        report = generate_weekly_report(
            test_db,
            week_ago.isoformat(),
            today.isoformat(),
        )

        summary = format_telegram_summary(report)

        assert "<b>Weekly Autonomy KPI Report</b>" in summary
        assert "Period:" in summary
        assert "Summary:" in summary
        assert "Lost Sales Risk:" in summary


class TestEmptyData:
    """Test behavior with empty/missing data."""

    def test_empty_database(self, tmp_path):
        """Verify graceful handling of empty database."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create minimal tables
        cursor.execute("""
            CREATE TABLE dim_sku (sku_key TEXT, active_flag INTEGER, kaspi_price_kzt REAL)
        """)
        cursor.execute("""
            CREATE TABLE fact_sales_daily (sku_key TEXT, sale_date TEXT, quantity INTEGER)
        """)
        cursor.execute("""
            CREATE TABLE fact_sales (sku_key TEXT, order_date TEXT, quantity INTEGER, unit_price REAL)
        """)
        cursor.execute("""
            CREATE TABLE fact_demand_estimates (sku_key TEXT, d_final REAL)
        """)
        cursor.execute("""
            CREATE TABLE fact_sku_metrics (sku_key TEXT, d30 REAL)
        """)
        cursor.execute("""
            CREATE TABLE fact_inventory_snapshot_size (sku_key TEXT, snapshot_date TEXT, current_stock INTEGER)
        """)
        cursor.execute("""
            CREATE TABLE fact_run_steps (step_id INTEGER, run_id INTEGER, step_name TEXT, output_file TEXT, started_at TEXT)
        """)
        conn.commit()
        conn.close()

        today = date.today()
        week_ago = today - timedelta(days=6)

        report = generate_weekly_report(
            db_path,
            week_ago.isoformat(),
            today.isoformat(),
        )

        # Should return empty report without errors
        assert report.total_skus_analyzed == 0
        assert len(report.top_sku_biases) == 0
        assert len(report.oos_metrics) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
