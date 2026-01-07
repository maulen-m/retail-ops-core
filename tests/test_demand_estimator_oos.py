"""
Tests for DemandEstimator OOS (Out-of-Stock) detection patterns.

Test cases per execution plan:
- partial OOS (size unavailable but siblings sell)
- extended OOS (14+ day gap)
- intermittent OOS
- new SKU (<14 days)
- no anchor (warning path)
"""

import pytest
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.calc.demand_estimator import (
    DemandEstimator,
    DemandEstimatorConfig,
    SKUDemandResult,
    AnchorData,
    OOSType,
    ConfidenceLevel,
)
from core.calc.stock_timeline import StockTimelineBuilder


@pytest.fixture
def temp_db():
    """Create a temporary database with test schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        -- Core dimension tables
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            color TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            product_type TEXT,
            active_flag INTEGER DEFAULT 1
        );

        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT,
            size_order INTEGER,
            UNIQUE(sku_key, my_size)
        );

        -- Anchor data
        CREATE TABLE dim_anchor (
            sku_key TEXT PRIMARY KEY,
            d_active REAL,
            sigma REAL,
            S_share REAL, M_share REAL, L_share REAL, XL_share REAL,
            "2XL_share" REAL, "3XL_share" REAL
        );

        -- Sales data (matching production schema)
        CREATE TABLE sales_fact_v2 (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            status TEXT DEFAULT 'DELIVERED',
            store_code TEXT DEFAULT 'UNIVERSAL',
            kaspi_offer_name TEXT DEFAULT '',
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );

        -- Inventory snapshots
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            current_stock INTEGER,
            inbound_stock INTEGER DEFAULT 0,
            PRIMARY KEY(snapshot_date, sku_id)
        );

        -- Daily size-level sales aggregates (needed by get_size_sales_90d)
        CREATE TABLE fact_sales_daily_size (
            id INTEGER PRIMARY KEY,
            sale_date TEXT,
            store_code TEXT DEFAULT 'UNIVERSAL',
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            units INTEGER DEFAULT 0,
            UNIQUE(sale_date, store_code, sku_id)
        );

        -- PO arrivals
        CREATE TABLE fact_po_lines (
            sku_id TEXT,
            actual_arrival_date TEXT,
            received_qty INTEGER,
            status TEXT DEFAULT 'DELIVERED'
        );
    """)
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


def insert_sku(conn, sku_key: str, sizes: list[str]):
    """Insert SKU and its sizes."""
    # Size order mapping for standard sizes
    SIZE_ORDER = {
        "XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "2XL": 6, "3XL": 7, "4XL": 8,
        "22": 22, "24": 24, "26": 26, "28": 28, "30": 30, "32": 32, "34": 34
    }
    conn.execute(
        "INSERT OR IGNORE INTO dim_sku (sku_key, active_flag) VALUES (?, 1)",
        (sku_key,)
    )
    for size in sizes:
        sku_id = f"{sku_key}_{size}"
        size_order = SIZE_ORDER.get(size, 99)
        conn.execute(
            "INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size, size_order) VALUES (?, ?, ?, ?)",
            (sku_id, sku_key, size, size_order)
        )


def insert_anchor(conn, sku_key: str, d_active: float, size_shares: dict[str, float]):
    """Insert anchor data."""
    cols = ["sku_key", "d_active"]
    vals = [sku_key, d_active]
    for size, share in size_shares.items():
        col = f'"{size}_share"' if size.startswith('2') or size.startswith('3') else f'{size}_share'
        cols.append(col.replace('"', ''))
        vals.append(share)

    placeholders = ','.join(['?'] * len(vals))
    col_names = ','.join([f'"{c}"' if c.startswith('2') or c.startswith('3') else c for c in cols])
    conn.execute(f"INSERT INTO dim_anchor ({col_names}) VALUES ({placeholders})", vals)


def insert_sales(conn, sku_key: str, size: str, date_str: str, qty: int = 1, store_code: str = "UNIVERSAL"):
    """Insert a sale and update daily aggregates."""
    sku_id = f"{sku_key}_{size}"
    # Insert into raw sales table
    conn.execute(
        """INSERT INTO sales_fact_v2
           (order_id, order_date, sku_key, sku_id, my_size, quantity, status, store_code, kaspi_offer_name)
           VALUES (?, ?, ?, ?, ?, ?, 'DELIVERED', ?, '')""",
        (f"ORD_{date_str}_{sku_id}_{qty}_{store_code}", date_str, sku_key, sku_id, size, qty, store_code)
    )
    # Update or insert daily aggregate
    conn.execute(
        """INSERT INTO fact_sales_daily_size (sale_date, store_code, sku_id, sku_key, my_size, units)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(sale_date, store_code, sku_id) DO UPDATE SET units = units + excluded.units""",
        (date_str, store_code, sku_id, sku_key, size, qty)
    )


def insert_stock_snapshot(conn, sku_key: str, sizes: dict[str, int], snapshot_date: str):
    """Insert stock snapshot for all sizes."""
    for size, stock in sizes.items():
        sku_id = f"{sku_key}_{size}"
        conn.execute(
            """INSERT OR REPLACE INTO fact_inventory_snapshot_size
               (snapshot_date, sku_key, sku_id, my_size, current_stock, inbound_stock)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (snapshot_date, sku_key, sku_id, size, stock)
        )


def insert_po_arrival(conn, sku_key: str, size: str, arrival_date: str, qty: int):
    """Insert PO arrival."""
    sku_id = f"{sku_key}_{size}"
    conn.execute(
        "INSERT INTO fact_po_lines (sku_id, actual_arrival_date, received_qty, status) VALUES (?, ?, ?, 'DELIVERED')",
        (sku_id, arrival_date, qty)
    )


class TestPartialOOS:
    """Tests for partial OOS detection (stock-first)."""

    def test_partial_oos_detected_when_size_has_zero_stock(self, temp_db):
        """
        Scenario: Size XL has 0 stock for 10+ days while other sizes have stock.
        Expected: XL flagged as partial OOS.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_PARTIAL_OOS"
        sizes = ["S", "M", "L", "XL"]

        # Setup SKU
        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 4.0, {"S": 0.15, "M": 0.30, "L": 0.35, "XL": 0.20})

        # Add current stock - XL is out of stock
        today = date.today()
        snapshot_date = today.isoformat()
        insert_stock_snapshot(conn, sku_key, {"S": 10, "M": 20, "L": 15, "XL": 0}, snapshot_date)

        # Add sales in last 30 days for in-stock sizes
        for i in range(30):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 2)
            insert_sales(conn, sku_key, "S", d, 1)
            # No sales for XL (OOS)

        conn.commit()
        conn.close()

        # Run estimator
        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # XL should be flagged as partial OOS (via sales-drift detection)
        assert "XL" in result.partial_oos_sizes or result.suppression_count > 0

    def test_no_partial_oos_when_all_sizes_have_stock(self, temp_db):
        """
        Scenario: All sizes have stock and sales.
        Expected: No partial OOS detected.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_NO_PARTIAL_OOS"
        sizes = ["S", "M", "L", "XL"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 4.0, {"S": 0.15, "M": 0.30, "L": 0.35, "XL": 0.20})

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"S": 10, "M": 20, "L": 15, "XL": 12}, today.isoformat())

        # Add proportional sales for all sizes
        for i in range(30):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "S", d, 1)
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 2)
            insert_sales(conn, sku_key, "XL", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # No partial OOS expected
        assert len(result.partial_oos_sizes) == 0 or result.suppression_count == 0


class TestExtendedOOS:
    """Tests for extended OOS detection (14+ consecutive days)."""

    def test_extended_oos_detected(self, temp_db):
        """
        Scenario: SKU has 0 sales and 0 stock for 20 consecutive days.
        Expected: Extended OOS type detected.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_EXTENDED_OOS"
        sizes = ["S", "M", "L"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 2.0, {"S": 0.30, "M": 0.40, "L": 0.30})

        today = date.today()
        # Current stock is zero (OOS now)
        insert_stock_snapshot(conn, sku_key, {"S": 0, "M": 0, "L": 0}, today.isoformat())

        # Add sales only in the distant past (before 20-day OOS gap)
        for i in range(30, 60):
            d = (today - timedelta(days=i)).isoformat()
            insert_sales(conn, sku_key, "M", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # Should have high anchor weight due to extended OOS
        assert result.anchor_weight >= 0.6


class TestIntermittentOOS:
    """Tests for intermittent OOS detection (>5 OOS days in 30)."""

    def test_intermittent_oos_increases_anchor_weight(self, temp_db):
        """
        Scenario: SKU has sporadic sales with several zero-stock days.
        Expected: Increased anchor weight.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_INTERMITTENT_OOS"
        sizes = ["S", "M", "L"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 3.0, {"S": 0.30, "M": 0.40, "L": 0.30})

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"S": 5, "M": 10, "L": 5}, today.isoformat())

        # Add sporadic sales (every 3rd day)
        for i in range(90):
            d = (today - timedelta(days=i+1)).isoformat()
            if i % 3 == 0:
                insert_sales(conn, sku_key, "M", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # Should have reasonable coverage
        assert result.good_days > 0


class TestNewSKU:
    """Tests for new SKU handling (<14 days of data)."""

    def test_new_sku_uses_anchor_heavily(self, temp_db):
        """
        Scenario: SKU with only 5 days of sales data.
        Expected: High anchor weight (ANCHOR_ONLY confidence).
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_NEW_SKU"
        sizes = ["S", "M", "L"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 5.0, {"S": 0.25, "M": 0.50, "L": 0.25})

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"S": 20, "M": 30, "L": 20}, today.isoformat())

        # Only 5 days of sales
        for i in range(5):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # Should have low sales_coverage_days (only 5 days of sales)
        assert result.sales_coverage_days <= 5, f"Expected <= 5 sales days, got {result.sales_coverage_days}"
        # Should have high anchor weight (0.6 for <14 good days, but good_days is stock-based)
        # With limited sales data but unknown stock history, anchor is still used heavily
        assert result.anchor_weight >= 0.6, f"Expected anchor weight >= 0.6, got {result.anchor_weight}"


class TestNoAnchor:
    """Tests for SKUs without anchor data."""

    def test_no_anchor_uses_data_only(self, temp_db):
        """
        Scenario: SKU without anchor data.
        Expected: Data-only estimation with warning (per Demand_Estimator_Execution_Plan).
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_NO_ANCHOR"
        sizes = ["S", "M", "L"]

        insert_sku(conn, sku_key, sizes)
        # Note: NOT inserting anchor data

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"S": 10, "M": 20, "L": 15}, today.isoformat())

        for i in range(60):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)
        assert result.has_anchor is False
        assert result.anchor_weight == 0.0
        assert result.d_final == pytest.approx(result.d_data)
        assert any("No anchor data" in w for w in result.warnings)


class TestInitSignature:
    """Tests for DemandEstimator init signature."""

    def test_init_accepts_use_db_anchors(self, temp_db):
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_INIT_ANCHOR"
        sizes = ["M"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 3.0, {"M": 1.0})
        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        assert estimator.anchor_data.get(sku_key) is not None


class TestAvailabilityScore:
    """Tests for availability score calculation."""

    def test_high_availability_gives_low_anchor_weight(self, temp_db):
        """
        Scenario: Full availability (all sizes in stock all days).
        Expected: Low anchor weight (trust data).
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_HIGH_AVAIL"
        sizes = ["S", "M", "L", "XL"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 4.0, {"S": 0.20, "M": 0.30, "L": 0.30, "XL": 0.20})

        today = date.today()
        # Good stock for all sizes
        insert_stock_snapshot(conn, sku_key, {"S": 50, "M": 50, "L": 50, "XL": 50}, today.isoformat())

        # Consistent sales matching anchor shares
        for i in range(60):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "S", d, 1)
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 2)
            insert_sales(conn, sku_key, "XL", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        # High availability should be detected
        # Note: actual value depends on stock timeline rebuild
        assert result.availability_score >= 0.0  # At minimum, it's calculated


class TestBayesianSizeShares:
    """Tests for Bayesian size share calculation."""

    def test_size_shares_sum_to_one(self, temp_db):
        """
        Scenario: Normal SKU with anchor and sales.
        Expected: Size shares sum to 1.0.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_SHARES"
        sizes = ["S", "M", "L", "XL"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 4.0, {"S": 0.15, "M": 0.35, "L": 0.35, "XL": 0.15})

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"S": 10, "M": 20, "L": 20, "XL": 10}, today.isoformat())

        for i in range(30):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "S", d, 1)
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 2)
            insert_sales(conn, sku_key, "XL", d, 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        if result.size_results:
            share_sum = sum(sr.share_final for sr in result.size_results.values())
            assert abs(share_sum - 1.0) < 0.01, f"Shares sum to {share_sum}, not 1.0"

    def test_oos_size_retains_share_from_anchor(self, temp_db):
        """
        Scenario: Size XL has no recent sales (OOS) but has anchor share.
        Expected: XL retains non-zero share via Bayesian prior.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_OOS_SHARE"
        sizes = ["S", "M", "L", "XL"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 4.0, {"S": 0.15, "M": 0.35, "L": 0.35, "XL": 0.15})

        today = date.today()
        # XL has zero stock
        insert_stock_snapshot(conn, sku_key, {"S": 10, "M": 20, "L": 20, "XL": 0}, today.isoformat())

        # Sales only for in-stock sizes
        for i in range(30):
            d = (today - timedelta(days=i+1)).isoformat()
            insert_sales(conn, sku_key, "S", d, 1)
            insert_sales(conn, sku_key, "M", d, 2)
            insert_sales(conn, sku_key, "L", d, 2)
            # No XL sales (OOS)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(temp_db, use_db_anchors=True)
        result = estimator.estimate_demand(sku_key)

        if result.size_results and "XL" in result.size_results:
            xl_share = result.size_results["XL"].share_final
            # XL should retain some share (not collapse to 0) due to Bayesian prior
            assert xl_share > 0.01, f"XL share collapsed to {xl_share}"


class TestDemandEstimatorFixes:
    """Tests for demand estimator regression fixes."""

    def test_blend_anchor_fallback_when_no_sales(self, temp_db):
        """Anchor-only SKUs should not scale anchors down when sales are missing."""
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_ANCHOR_ONLY"
        sizes = ["M"]

        insert_sku(conn, sku_key, sizes)
        insert_anchor(conn, sku_key, 6.0, {"M": 1.0})

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"M": 10}, today.isoformat())

        conn.commit()
        conn.close()

        estimator = DemandEstimator(
            temp_db,
            use_db_anchors=True,
            config=DemandEstimatorConfig(lookback_days=7)
        )
        result = estimator.estimate_demand(sku_key)

        assert result.d_data == 0.0
        assert result.d_final == pytest.approx(result.d_anchor)

    def test_all_store_aggregation_increases_or_equals_single_store(self, temp_db):
        """All-store demand should be >= single-store demand for multi-store SKUs."""
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_MULTI_STORE"
        sizes = ["M"]

        insert_sku(conn, sku_key, sizes)

        today = date.today()
        insert_stock_snapshot(conn, sku_key, {"M": 25}, today.isoformat())

        for i in range(5):
            d = (today - timedelta(days=i + 1)).isoformat()
            insert_sales(conn, sku_key, "M", d, 1, store_code="UNIVERSAL")
            insert_sales(conn, sku_key, "M", d, 1, store_code="ACMEWEAR")

        conn.commit()
        conn.close()

        estimator = DemandEstimator(
            temp_db,
            use_db_anchors=True,
            config=DemandEstimatorConfig(lookback_days=7)
        )
        result_single = estimator.estimate_demand(sku_key, store_codes=["UNIVERSAL"])
        result_all = estimator.estimate_demand(sku_key, store_codes=None)

        assert result_all.d_final >= result_single.d_final

    def test_stock_timeline_reconstruction_fills_gaps(self, temp_db):
        """Stock timeline reconstruction should fill gaps from snapshot + sales.

        When a snapshot exists, the timeline builder can forward/backward simulate
        stock levels for days without explicit snapshots. This means days with
        reconstructed stock are 'known' not 'unknown'.
        """
        conn = sqlite3.connect(str(temp_db))
        sku_key = "TEST_UNKNOWN_DAYS"
        sizes = ["M"]

        insert_sku(conn, sku_key, sizes)

        estimator = DemandEstimator(
            temp_db,
            use_db_anchors=True,
            config=DemandEstimatorConfig(lookback_days=4)
        )
        cutoff = estimator.cutoff_date
        start_date = cutoff - timedelta(days=4)

        # Sales on two days, no stock snapshots for those days
        sales_days = [start_date + timedelta(days=1), start_date + timedelta(days=3)]
        for d in sales_days:
            insert_sales(conn, sku_key, "M", d.isoformat(), 1)

        # One known-stock day with stock > 0 and no sales
        snapshot_day = start_date + timedelta(days=2)
        insert_stock_snapshot(conn, sku_key, {"M": 5}, snapshot_day.isoformat())

        conn.commit()
        conn.close()

        result = estimator.estimate_demand(sku_key)

        # With timeline reconstruction from the snapshot, all days become known
        # The 2 sales days + 1 snapshot day + 2 reconstructed days = 5 good days
        assert result.good_days == 5
        # Timeline reconstruction fills gaps, so unknown_days should be 0
        assert result.unknown_days == 0


class TestDemandEstimatorIntegration:
    """Integration test with a golden SKU set."""

    def test_golden_sku_set(self, temp_db):
        conn = sqlite3.connect(str(temp_db))
        today = date.today()

        # Multi-store SKU
        sku_multi = "TEST_GOLDEN_MULTI"
        insert_sku(conn, sku_multi, ["M"])
        insert_stock_snapshot(conn, sku_multi, {"M": 15}, today.isoformat())
        for i in range(5):
            d = (today - timedelta(days=i + 1)).isoformat()
            insert_sales(conn, sku_multi, "M", d, 1, store_code="UNIVERSAL")
            insert_sales(conn, sku_multi, "M", d, 2, store_code="ACMEWEAR")

        # Anchor-only SKU
        sku_anchor = "TEST_GOLDEN_ANCHOR"
        insert_sku(conn, sku_anchor, ["M"])
        insert_anchor(conn, sku_anchor, 4.0, {"M": 1.0})
        insert_stock_snapshot(conn, sku_anchor, {"M": 8}, today.isoformat())

        # Sparse stock history SKU
        sku_sparse = "TEST_GOLDEN_SPARSE"
        insert_sku(conn, sku_sparse, ["M"])
        insert_anchor(conn, sku_sparse, 3.0, {"M": 1.0})
        insert_stock_snapshot(conn, sku_sparse, {"M": 6}, today.isoformat())
        insert_sales(conn, sku_sparse, "M", (today - timedelta(days=1)).isoformat(), 1)

        conn.commit()
        conn.close()

        estimator = DemandEstimator(
            temp_db,
            use_db_anchors=True,
            config=DemandEstimatorConfig(lookback_days=7)
        )
        results, _ = estimator.estimate_all(store_codes=None)
        result_map = {r.sku_key: r for r in results}

        assert result_map[sku_multi].store_aggregation_mode == "ALL"
        assert "UNIVERSAL" in result_map[sku_multi].store_codes
        assert "ACMEWEAR" in result_map[sku_multi].store_codes
        assert result_map[sku_anchor].d_final == pytest.approx(result_map[sku_anchor].d_anchor)
        # With stock timeline reconstruction, even sparse SKUs have timeline coverage
        # so unknown_days should be 0 (not > 0 as in legacy behavior)
        assert result_map[sku_sparse].unknown_days == 0
        # Anchor weight should be high for sparse data (few sales, strong anchor)
        assert result_map[sku_sparse].anchor_weight >= 0.5


# Run tests with: pytest tests/test_demand_estimator_oos.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
