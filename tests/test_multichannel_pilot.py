"""
Tests for Multi-Channel Pilot (Part 7C)

Tests:
- Pilot SKU configuration loading
- Channel weight application
- Recommendation generation
- KPI calculation
- Export functionality
"""

import json
import os
import sqlite3
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_multichannel_pilot import (
    PilotSKU,
    ChannelRecommendation,
    PilotKPI,
    load_pilot_config,
    save_pilot_config,
    get_pilot_skus,
    init_pilot_config,
    generate_channel_recommendations,
    calculate_pilot_kpis,
    export_pilot_recommendations,
    export_pilot_kpis,
    generate_pilot_summary,
    get_default_pilot_config,
)


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with required tables."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create dim_sku
    cursor.execute("""
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            sku_name TEXT,
            base_cost_cny REAL DEFAULT 0,
            cogs_kzt REAL DEFAULT 0
        )
    """)

    # Create fact_sku_metrics
    cursor.execute("""
        CREATE TABLE fact_sku_metrics (
            sku_key TEXT PRIMARY KEY,
            d30 REAL DEFAULT 0,
            current_stock INTEGER DEFAULT 0,
            inbound_stock INTEGER DEFAULT 0,
            rop INTEGER DEFAULT 0,
            suggested_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'OK',
            roic_pct REAL DEFAULT 0
        )
    """)

    # Create fact_demand_estimates
    cursor.execute("""
        CREATE TABLE fact_demand_estimates (
            sku_key TEXT PRIMARY KEY,
            d_final REAL DEFAULT 0
        )
    """)

    # Insert test data
    cursor.execute("""
        INSERT INTO dim_sku (sku_key, sku_name, cogs_kzt)
        VALUES ('SKU_A', 'Test SKU A', 5000)
    """)
    cursor.execute("""
        INSERT INTO dim_sku (sku_key, sku_name, cogs_kzt)
        VALUES ('SKU_B', 'Test SKU B', 3000)
    """)

    cursor.execute("""
        INSERT INTO fact_sku_metrics (sku_key, d30, current_stock, rop, suggested_order, status, roic_pct)
        VALUES ('SKU_A', 5.0, 50, 30, 100, 'REORDER', 25.0)
    """)
    cursor.execute("""
        INSERT INTO fact_sku_metrics (sku_key, d30, current_stock, rop, suggested_order, status, roic_pct)
        VALUES ('SKU_B', 3.0, 20, 15, 50, 'OK', 18.0)
    """)

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def pilot_config_file(tmp_path):
    """Create a test pilot config file."""
    config = {
        "version": "1.0",
        "max_pilot_skus": 20,
        "default_kaspi_weight": 0.7,
        "default_wb_weight": 0.3,
        "pilot_skus": [
            {
                "sku_key": "SKU_A",
                "kaspi_weight": 0.6,
                "wb_weight": 0.4,
                "active": True,
                "notes": "Test pilot A"
            },
            {
                "sku_key": "SKU_B",
                "kaspi_weight": 0.8,
                "wb_weight": 0.2,
                "active": True,
                "notes": "Test pilot B"
            },
            {
                "sku_key": "SKU_INACTIVE",
                "kaspi_weight": 0.5,
                "wb_weight": 0.5,
                "active": False,
                "notes": "Inactive pilot"
            }
        ]
    }

    config_path = tmp_path / "pilot_skus.json"
    with open(config_path, 'w') as f:
        json.dump(config, f)

    return config_path


class TestPilotConfiguration:
    """Test pilot SKU configuration loading."""

    def test_load_pilot_config_from_file(self, pilot_config_file):
        """Test loading config from JSON file."""
        config = load_pilot_config(pilot_config_file)

        assert config["version"] == "1.0"
        assert config["max_pilot_skus"] == 20
        assert len(config["pilot_skus"]) == 3

    def test_get_pilot_skus_filters_inactive(self, pilot_config_file):
        """Test that inactive SKUs are filtered out."""
        config = load_pilot_config(pilot_config_file)
        skus = get_pilot_skus(config)

        assert len(skus) == 2
        assert all(s.active for s in skus)
        assert "SKU_INACTIVE" not in [s.sku_key for s in skus]

    def test_get_default_pilot_config(self):
        """Test default config generation."""
        config = get_default_pilot_config()

        assert "version" in config
        assert "pilot_skus" in config
        assert config["max_pilot_skus"] == 20

    def test_save_pilot_config(self, tmp_path):
        """Test saving config to file."""
        config = get_default_pilot_config()
        config["pilot_skus"] = [{"sku_key": "NEW_SKU", "active": True}]

        config_path = tmp_path / "new_config.json"
        result = save_pilot_config(config, config_path)

        assert result is True
        assert config_path.exists()

        # Reload and verify
        loaded = load_pilot_config(config_path)
        assert len(loaded["pilot_skus"]) == 1
        assert loaded["pilot_skus"][0]["sku_key"] == "NEW_SKU"

    def test_init_pilot_config_creates_table(self, tmp_path):
        """Test database table initialization."""
        db_path = tmp_path / "test.db"

        result = init_pilot_config(db_path)
        assert result is True

        # Verify table exists
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_pilot_skus'"
        ).fetchall()
        conn.close()

        assert len(tables) == 1


class TestChannelWeightedRecommendations:
    """Test channel-weighted recommendation generation."""

    def test_generate_channel_recommendations(self, test_db):
        """Test basic recommendation generation."""
        pilot_skus = [
            PilotSKU(sku_key="SKU_A", kaspi_weight=0.7, wb_weight=0.3)
        ]

        recommendations = generate_channel_recommendations(test_db, pilot_skus)

        assert len(recommendations) == 2  # One for each channel

        kaspi_rec = next(r for r in recommendations if r.channel == "KASPI")
        wb_rec = next(r for r in recommendations if r.channel == "WB")

        # Check weights applied correctly (100 total * 0.7 = 70, 100 * 0.3 = 30)
        assert kaspi_rec.recommended_qty == 70
        assert wb_rec.recommended_qty == 30

    def test_channel_split_rounding(self, test_db):
        """Test that rounding doesn't lose units."""
        pilot_skus = [
            PilotSKU(sku_key="SKU_A", kaspi_weight=0.33, wb_weight=0.67)
        ]

        recommendations = generate_channel_recommendations(test_db, pilot_skus)

        total_recommended = sum(r.recommended_qty for r in recommendations)
        # Original was 100, should not lose units due to rounding
        assert total_recommended == 100

    def test_multiple_skus_recommendations(self, test_db):
        """Test recommendations for multiple SKUs."""
        pilot_skus = [
            PilotSKU(sku_key="SKU_A", kaspi_weight=0.6, wb_weight=0.4),
            PilotSKU(sku_key="SKU_B", kaspi_weight=0.8, wb_weight=0.2),
        ]

        recommendations = generate_channel_recommendations(test_db, pilot_skus)

        assert len(recommendations) == 4  # 2 channels x 2 SKUs

        # Check SKU_A split (100 * 0.6 = 60, 100 * 0.4 = 40)
        sku_a_kaspi = next(r for r in recommendations if r.sku_key == "SKU_A" and r.channel == "KASPI")
        assert sku_a_kaspi.recommended_qty == 60

        # Check SKU_B split (50 * 0.8 = 40, 50 * 0.2 = 10)
        sku_b_wb = next(r for r in recommendations if r.sku_key == "SKU_B" and r.channel == "WB")
        assert sku_b_wb.recommended_qty == 10


class TestPilotKPIs:
    """Test pilot KPI calculation."""

    @pytest.fixture
    def test_db_with_sales(self, tmp_path):
        """Create test DB with sales data."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create tables
        cursor.execute("""
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                cogs_kzt REAL DEFAULT 0,
                base_cost_cny REAL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE fact_sales_daily (
                id INTEGER PRIMARY KEY,
                sku_key TEXT,
                sale_date TEXT,
                channel TEXT,
                quantity INTEGER,
                seller_price REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE fact_inventory_snapshot_size (
                sku_key TEXT,
                snapshot_date TEXT,
                current_stock INTEGER
            )
        """)

        # Insert test data
        cursor.execute("INSERT INTO dim_sku VALUES ('SKU_A', 5000, 64)")

        today = date.today()
        for i in range(7):
            sale_date = (today - timedelta(days=i)).isoformat()
            # Kaspi sales
            cursor.execute("""
                INSERT INTO fact_sales_daily (sku_key, sale_date, channel, quantity, seller_price)
                VALUES ('SKU_A', ?, 'KASPI', 10, 10000)
            """, (sale_date,))
            # WB sales
            cursor.execute("""
                INSERT INTO fact_sales_daily (sku_key, sale_date, channel, quantity, seller_price)
                VALUES ('SKU_A', ?, 'WB', 5, 12000)
            """, (sale_date,))
            # Inventory
            cursor.execute("""
                INSERT INTO fact_inventory_snapshot_size (sku_key, snapshot_date, current_stock)
                VALUES ('SKU_A', ?, ?)
            """, (sale_date, 50 if i > 0 else 0))  # Day 0 is OOS

        conn.commit()
        conn.close()

        return db_path

    def test_calculate_pilot_kpis(self, test_db_with_sales):
        """Test KPI calculation."""
        pilot_skus = [PilotSKU(sku_key="SKU_A", kaspi_weight=0.7, wb_weight=0.3)]

        kpis = calculate_pilot_kpis(test_db_with_sales, pilot_skus, period_days=7)

        assert len(kpis) == 2  # Kaspi + WB

        kaspi_kpi = next(k for k in kpis if k.channel == "KASPI")
        wb_kpi = next(k for k in kpis if k.channel == "WB")

        # Check Kaspi: 10 units/day * 7 days = 70 units
        assert kaspi_kpi.units_sold == 70
        assert kaspi_kpi.revenue_kzt == 700000  # 70 * 10000

        # Check WB: 5 units/day * 7 days = 35 units
        assert wb_kpi.units_sold == 35
        assert wb_kpi.revenue_kzt == 420000  # 35 * 12000

    def test_kpi_profit_calculation(self, test_db_with_sales):
        """Test profit margin calculation."""
        pilot_skus = [PilotSKU(sku_key="SKU_A", kaspi_weight=0.7, wb_weight=0.3)]

        kpis = calculate_pilot_kpis(test_db_with_sales, pilot_skus, period_days=7)

        kaspi_kpi = next(k for k in kpis if k.channel == "KASPI")

        # Revenue: 700000, COGS: 70 * 5000 = 350000, Profit: 350000
        assert kaspi_kpi.cogs_kzt == 350000
        assert kaspi_kpi.gross_profit_kzt == 350000
        assert kaspi_kpi.profit_margin_pct == pytest.approx(50.0)


class TestPilotExports:
    """Test pilot export functionality."""

    def test_export_pilot_recommendations(self, tmp_path):
        """Test recommendation CSV export."""
        recommendations = [
            ChannelRecommendation(
                sku_key="SKU_A",
                channel="KASPI",
                recommended_qty=70,
                total_value_kzt=350000
            ),
            ChannelRecommendation(
                sku_key="SKU_A",
                channel="WB",
                recommended_qty=30,
                total_value_kzt=150000
            ),
        ]

        output_path = tmp_path / "test_recs.csv"
        result = export_pilot_recommendations(recommendations, output_path)

        assert result == output_path
        assert output_path.exists()

        # Verify content
        with open(output_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 3  # Header + 2 rows

    def test_export_pilot_kpis(self, tmp_path):
        """Test KPI CSV export."""
        kpis = [
            PilotKPI(
                sku_key="SKU_A",
                channel="KASPI",
                period_start="2025-12-18",
                period_end="2025-12-25",
                units_sold=70,
                revenue_kzt=700000,
                cogs_kzt=350000,
                gross_profit_kzt=350000,
                profit_margin_pct=50.0
            )
        ]

        output_path = tmp_path / "test_kpis.csv"
        result = export_pilot_kpis(kpis, output_path)

        assert result == output_path
        assert output_path.exists()


class TestPilotSummary:
    """Test pilot summary generation."""

    def test_generate_pilot_summary(self):
        """Test summary statistics."""
        recommendations = [
            ChannelRecommendation(sku_key="A", channel="KASPI", recommended_qty=70, total_value_kzt=350000, status="REORDER"),
            ChannelRecommendation(sku_key="A", channel="WB", recommended_qty=30, total_value_kzt=150000, status="OK"),
        ]

        kpis = [
            PilotKPI(sku_key="A", channel="KASPI", revenue_kzt=700000, gross_profit_kzt=350000, period_start="", period_end=""),
            PilotKPI(sku_key="A", channel="WB", revenue_kzt=300000, gross_profit_kzt=150000, period_start="", period_end=""),
        ]

        summary = generate_pilot_summary(recommendations, kpis)

        assert summary["total_skus"] == 1
        assert summary["total_recommended_qty"] == 100
        assert summary["total_recommended_value_kzt"] == 500000
        assert summary["kaspi_total_revenue"] == 700000
        assert summary["wb_total_revenue"] == 300000
        assert summary["reorder_count"] == 1

        # Check percentages
        assert summary["kaspi_revenue_pct"] == pytest.approx(70.0)
        assert summary["wb_revenue_pct"] == pytest.approx(30.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
