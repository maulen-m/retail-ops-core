"""
TASK-189: Tests for Phase 10 v2 query functions

Tests the new query functions that use stock_ledger, sales_fact_v2,
and po_header/po_line tables.
"""

import pytest
import tempfile
from datetime import date, timedelta
from pathlib import Path

from core.db import get_db
from core.db.queries import (
    get_size_current_stock_v2,
    get_size_inbound_v2,
    get_size_sales_90d_v2,
    get_size_sales_history_v2,
    get_size_stock_history_v2,
    get_sku_age_days_v2,
    get_po_lines_for_sku,
    get_stock_movement_summary,
)


@pytest.fixture
def test_db():
    """Create a temporary test database with Phase 10 schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    with get_db(db_path) as conn:
        # Create Phase 10 tables
        conn.executescript("""
            -- Dimension table for SKU sizes
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                size_order INTEGER DEFAULT 0
            );

            -- Stock ledger (event-sourced)
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                sku_key TEXT,
                sku_id TEXT NOT NULL,
                my_size TEXT,
                store_code TEXT DEFAULT 'UNIVERSAL',
                qty_change INTEGER NOT NULL,
                running_balance INTEGER,
                reference_id TEXT,
                reference_type TEXT,
                kaspi_offer_name TEXT,
                notes TEXT,
                input_source TEXT DEFAULT 'SYSTEM',
                created_by TEXT DEFAULT 'system',
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Sales fact v2 (deduplicated)
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                sku_key TEXT,
                sku_id TEXT NOT NULL,
                my_size TEXT,
                store_code TEXT DEFAULT 'UNIVERSAL',
                kaspi_offer_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL,
                total_kzt REAL,
                delivery_address TEXT,
                status TEXT DEFAULT 'COMPLETED',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
            );

            -- PO header
            CREATE TABLE po_header (
                po_id TEXT PRIMARY KEY,
                supplier_code TEXT,
                status TEXT DEFAULT 'DRAFT',
                message_date TEXT,
                order_date TEXT,
                ship_date_seller TEXT,
                ship_date_cargo TEXT,
                alm_arrival_date TEXT,
                ast_arrival_nom TEXT,
                alm_arrival_real TEXT,
                ast_arrival_real TEXT,
                archive_alm_arrival TEXT,
                archive_ast_arrival TEXT,
                fx_rate_cny_actual REAL,
                fx_rate_usd_kzt REAL,
                weight_nom_kg REAL,
                weight_real_kg REAL,
                total_cost_kzt_supplier REAL,
                cargo_cost_usd REAL,
                cargo_cost_kzt REAL,
                notes TEXT,
                created_by TEXT DEFAULT 'system',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT
            );

            -- PO line
            CREATE TABLE po_line (
                po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_id TEXT NOT NULL,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                order_qty INTEGER DEFAULT 0,
                received_qty INTEGER DEFAULT 0,
                unit_cost_cny REAL,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (po_id) REFERENCES po_header(po_id)
            );
        """)

        # Insert test data
        # SKU sizes
        sizes = [("S", 1), ("M", 2), ("L", 3), ("XL", 4)]
        for size, order in sizes:
            conn.execute("""
                INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
                VALUES (?, 'TEST_SKU', ?, ?)
            """, (f"TEST_SKU_{size}", size, order))

        # Stock ledger events
        today = date.today()
        # Initial stock: S=10, M=20, L=30, XL=40
        for size, qty in [("S", 10), ("M", 20), ("L", 30), ("XL", 40)]:
            conn.execute("""
                INSERT INTO stock_ledger (event_date, event_type, sku_key, sku_id, my_size, store_code, qty_change, running_balance)
                VALUES (?, 'INITIAL', 'TEST_SKU', ?, ?, 'UNIVERSAL', ?, ?)
            """, ((today - timedelta(days=30)).isoformat(), f"TEST_SKU_{size}", size, qty, qty))

        # Sales: S=-2, M=-5, L=-10 (from 10 days ago)
        for size, qty in [("S", 2), ("M", 5), ("L", 10)]:
            conn.execute("""
                INSERT INTO stock_ledger (event_date, event_type, sku_key, sku_id, my_size, store_code, qty_change, running_balance, reference_id)
                VALUES (?, 'SALE', 'TEST_SKU', ?, ?, 'UNIVERSAL', ?, ?, 'ORD-001')
            """, ((today - timedelta(days=10)).isoformat(), f"TEST_SKU_{size}", size, -qty, None))

        # Sales fact v2 records
        conn.execute("""
            INSERT INTO sales_fact_v2 (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, status)
            VALUES ('ORD-001', ?, 'TEST_SKU', 'TEST_SKU_S', 'S', 'UNIVERSAL', 2, 'COMPLETED')
        """, ((today - timedelta(days=10)).isoformat(),))
        conn.execute("""
            INSERT INTO sales_fact_v2 (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, status)
            VALUES ('ORD-002', ?, 'TEST_SKU', 'TEST_SKU_M', 'M', 'UNIVERSAL', 5, 'COMPLETED')
        """, ((today - timedelta(days=10)).isoformat(),))
        conn.execute("""
            INSERT INTO sales_fact_v2 (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, status)
            VALUES ('ORD-003', ?, 'TEST_SKU', 'TEST_SKU_L', 'L', 'UNIVERSAL', 10, 'COMPLETED')
        """, ((today - timedelta(days=10)).isoformat(),))

        # PO header and lines
        conn.execute("""
            INSERT INTO po_header (po_id, supplier_code, status, created_at)
            VALUES ('PO-001', 'SUPPLIER-A', 'IN_TRANSIT', datetime('now'))
        """)
        for size, qty in [("S", 20), ("M", 30), ("L", 0), ("XL", 10)]:
            if qty > 0:
                conn.execute("""
                    INSERT INTO po_line (po_id, sku_key, sku_id, my_size, order_qty, received_qty, status)
                    VALUES ('PO-001', 'TEST_SKU', ?, ?, ?, 0, 'PENDING')
                """, (f"TEST_SKU_{size}", size, qty))

        conn.commit()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


class TestGetSizeCurrentStockV2:
    """Tests for get_size_current_stock_v2."""

    def test_returns_current_balance(self, test_db):
        """Test that it returns correct balance from ledger events."""
        result = get_size_current_stock_v2("TEST_SKU", db_path=test_db)

        # Initial - Sales = Current
        assert result["S"] == 10 - 2  # 8
        assert result["M"] == 20 - 5  # 15
        assert result["L"] == 30 - 10  # 20
        assert result["XL"] == 40  # No sales

    def test_returns_empty_for_unknown_sku(self, test_db):
        """Test that it returns empty dict for unknown SKU."""
        result = get_size_current_stock_v2("UNKNOWN_SKU", db_path=test_db)
        assert result == {}


class TestGetSizeInboundV2:
    """Tests for get_size_inbound_v2."""

    def test_returns_pending_po_qty(self, test_db):
        """Test that it returns pending quantities from PO lines."""
        result = get_size_inbound_v2("TEST_SKU", db_path=test_db)

        assert result["S"] == 20
        assert result["M"] == 30
        assert result["L"] == 0
        assert result["XL"] == 10

    def test_excludes_closed_pos(self, test_db):
        """Test that closed POs are excluded."""
        with get_db(test_db) as conn:
            conn.execute("UPDATE po_header SET status = 'CLOSED' WHERE po_id = 'PO-001'")
            conn.commit()

        result = get_size_inbound_v2("TEST_SKU", db_path=test_db)
        assert all(qty == 0 for qty in result.values())


class TestGetSizeSales90dV2:
    """Tests for get_size_sales_90d_v2."""

    def test_returns_sales_totals(self, test_db):
        """Test that it returns correct sales totals from sales_fact_v2."""
        result = get_size_sales_90d_v2("TEST_SKU", db_path=test_db)

        assert result["S"] == 2
        assert result["M"] == 5
        assert result["L"] == 10
        assert result["XL"] == 0

    def test_excludes_returned_sales(self, test_db):
        """Test that returned sales are excluded."""
        with get_db(test_db) as conn:
            conn.execute("UPDATE sales_fact_v2 SET status = 'RETURNED' WHERE order_id = 'ORD-001'")
            conn.commit()

        result = get_size_sales_90d_v2("TEST_SKU", db_path=test_db)
        assert result["S"] == 0  # Excluded


class TestGetSizeSalesHistoryV2:
    """Tests for get_size_sales_history_v2."""

    def test_returns_daily_sales_list(self, test_db):
        """Test that it returns daily sales as lists."""
        result = get_size_sales_history_v2("TEST_SKU", days=30, db_path=test_db)

        # Should have 31 days of data (days+1)
        assert len(result["S"]) == 31
        assert len(result["M"]) == 31

        # Sum should match totals
        assert sum(result["S"]) == 2
        assert sum(result["M"]) == 5
        assert sum(result["L"]) == 10

    def test_fills_missing_days_with_zero(self, test_db):
        """Test that days without sales are filled with 0."""
        result = get_size_sales_history_v2("TEST_SKU", days=30, db_path=test_db)

        # Most days should be 0
        zero_count = sum(1 for x in result["S"] if x == 0)
        assert zero_count >= 28  # At least 28 zero days


class TestGetSizeStockHistoryV2:
    """Tests for get_size_stock_history_v2."""

    def test_returns_daily_balances(self, test_db):
        """Test that it calculates running balances correctly."""
        result = get_size_stock_history_v2("TEST_SKU", days=30, db_path=test_db)

        # Should have 31 days
        assert len(result["S"]) == 31

        # Last day should match current stock
        assert result["S"][-1] == 8  # 10 - 2
        assert result["M"][-1] == 15  # 20 - 5
        assert result["L"][-1] == 20  # 30 - 10
        assert result["XL"][-1] == 40  # No changes


class TestGetSkuAgeDaysV2:
    """Tests for get_sku_age_days_v2."""

    def test_returns_days_since_first_sale(self, test_db):
        """Test that it returns correct age from sales_fact_v2."""
        result = get_sku_age_days_v2("TEST_SKU", db_path=test_db)

        # First sale was 10 days ago
        assert result == 10

    def test_returns_zero_for_no_sales(self, test_db):
        """Test that it returns 0 for SKU with no sales."""
        result = get_sku_age_days_v2("UNKNOWN_SKU", db_path=test_db)
        assert result == 0


class TestGetPOLinesForSku:
    """Tests for get_po_lines_for_sku."""

    def test_returns_po_lines(self, test_db):
        """Test that it returns PO lines with header info."""
        result = get_po_lines_for_sku("TEST_SKU", db_path=test_db)

        assert len(result) == 3  # S, M, XL (L has 0 qty)
        assert all("po_id" in r for r in result)
        assert all("po_status" in r for r in result)
        assert all("supplier_code" in r for r in result)

    def test_filters_by_status(self, test_db):
        """Test that it filters by line status."""
        with get_db(test_db) as conn:
            conn.execute("UPDATE po_line SET status = 'RECEIVED' WHERE my_size = 'S'")
            conn.commit()

        result = get_po_lines_for_sku("TEST_SKU", status="PENDING", db_path=test_db)
        assert len(result) == 2  # M and XL only


class TestGetStockMovementSummary:
    """Tests for get_stock_movement_summary."""

    def test_returns_movement_summary(self, test_db):
        """Test that it returns complete movement summary."""
        result = get_stock_movement_summary("TEST_SKU", days=30, db_path=test_db)

        # Current stock
        assert result["current_stock"]["S"] == 8
        assert result["current_stock"]["M"] == 15

        # Movement totals
        assert "INITIAL" in result["movements"]
        assert "SALE" in result["movements"]

        # By size breakdown
        assert "S" in result["by_size"]
        assert "SALE" in result["by_size"]["S"]
        assert result["by_size"]["S"]["SALE"] == -2
