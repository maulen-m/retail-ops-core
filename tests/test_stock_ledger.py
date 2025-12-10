"""
TASK-173: Tests for Stock Ledger Module (Phase 10)

Tests the event-sourced stock tracking functions in core/db/ledger.py.

10 tests covering:
- Event creation (sale, inbound, adjustment)
- Balance calculations
- Snapshot rebuilding
- Edge cases (negative balance, event date vs created_at)
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os

from core.db.ledger import (
    add_ledger_event,
    get_stock_balance,
    get_stock_balances_all,
    rebuild_snapshot_from_ledger,
    get_ledger_events,
    count_ledger_events,
    get_event_summary,
    VALID_EVENT_TYPES,
)


@pytest.fixture
def test_db():
    """Create a temporary database with required schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create stock_ledger table
    conn.execute("""
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date DATE NOT NULL,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create po_header table
    conn.execute("""
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'DRAFT',
            supplier_code TEXT DEFAULT 'SUPP_A'
        )
    """)

    # Create po_line table
    conn.execute("""
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            unit_cost_cny REAL NOT NULL,
            FOREIGN KEY (po_id) REFERENCES po_header(po_id)
        )
    """)

    # Create dim_sku_size table
    conn.execute("""
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            size_order INTEGER
        )
    """)

    # Create fact_inventory_snapshot_size table (matches existing schema - no store_code)
    conn.execute("""
        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER DEFAULT 0,
            inbound_stock INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(sku_id, snapshot_date)
        )
    """)

    # Seed dim_sku_size with test data
    test_sizes = [
        ("TEST_SKU_KEY_S", "TEST_SKU_KEY", "S", 1),
        ("TEST_SKU_KEY_M", "TEST_SKU_KEY", "M", 2),
        ("TEST_SKU_KEY_L", "TEST_SKU_KEY", "L", 3),
        ("TEST_SKU_KEY_XL", "TEST_SKU_KEY", "XL", 4),
    ]
    conn.executemany("""
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
        VALUES (?, ?, ?, ?)
    """, test_sizes)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


class TestAddLedgerEvent:
    """Tests for add_ledger_event function."""

    def test_add_event_sale(self, test_db):
        """Test adding a SALE event decreases stock."""
        ledger_id = add_ledger_event(
            event_type="SALE",
            sku_id="TEST_SKU_KEY_M",
            qty_change=-1,
            event_date=date.today(),
            reference_id="ORDER-001",
            reference_type="SALE",
            kaspi_offer_name="Test Product M",
            db_path=test_db,
        )

        assert ledger_id is not None
        assert ledger_id > 0

        # Verify event was stored correctly
        events = get_ledger_events(sku_id="TEST_SKU_KEY_M", db_path=test_db)
        assert len(events) == 1
        assert events[0]["event_type"] == "SALE"
        assert events[0]["qty_change"] == -1
        assert events[0]["reference_id"] == "ORDER-001"
        assert events[0]["kaspi_offer_name"] == "Test Product M"

    def test_add_event_inbound(self, test_db):
        """Test adding an INBOUND event increases stock."""
        ledger_id = add_ledger_event(
            event_type="INBOUND",
            sku_id="TEST_SKU_KEY_L",
            qty_change=50,
            event_date=date.today(),
            reference_id="PO-2025-001",
            reference_type="PO",
            db_path=test_db,
        )

        assert ledger_id is not None

        events = get_ledger_events(sku_id="TEST_SKU_KEY_L", db_path=test_db)
        assert len(events) == 1
        assert events[0]["event_type"] == "INBOUND"
        assert events[0]["qty_change"] == 50
        assert events[0]["reference_type"] == "PO"

    def test_add_event_adjustment(self, test_db):
        """Test adding an ADJUSTMENT event."""
        # Positive adjustment
        ledger_id = add_ledger_event(
            event_type="ADJUSTMENT",
            sku_id="TEST_SKU_KEY_XL",
            qty_change=5,
            event_date=date.today(),
            notes="Found 5 units in warehouse",
            input_source="MANUAL",
            created_by="adil",
            db_path=test_db,
        )

        assert ledger_id is not None

        events = get_ledger_events(sku_id="TEST_SKU_KEY_XL", db_path=test_db)
        assert len(events) == 1
        assert events[0]["event_type"] == "ADJUSTMENT"
        assert events[0]["qty_change"] == 5
        assert events[0]["notes"] == "Found 5 units in warehouse"
        assert events[0]["input_source"] == "MANUAL"

    def test_add_event_invalid_type(self, test_db):
        """Test that invalid event type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            add_ledger_event(
                event_type="INVALID_TYPE",
                sku_id="TEST_SKU_KEY_M",
                qty_change=10,
                event_date=date.today(),
                db_path=test_db,
            )

        assert "Invalid event_type" in str(exc_info.value)


class TestGetStockBalance:
    """Tests for get_stock_balance function."""

    def test_get_balance_empty(self, test_db):
        """Test balance is 0 for SKU with no events."""
        balance = get_stock_balance("TEST_SKU_KEY_S", db_path=test_db)
        assert balance == 0

    def test_get_balance_after_events(self, test_db):
        """Test balance calculation after multiple events."""
        today = date.today()

        # Initial stock: +100
        add_ledger_event("INITIAL", "TEST_SKU_KEY_M", 100, today, db_path=test_db)

        # Sale: -3
        add_ledger_event("SALE", "TEST_SKU_KEY_M", -3, today, db_path=test_db)

        # Another sale: -2
        add_ledger_event("SALE", "TEST_SKU_KEY_M", -2, today, db_path=test_db)

        balance = get_stock_balance("TEST_SKU_KEY_M", db_path=test_db)
        assert balance == 95  # 100 - 3 - 2

    def test_balance_multiple_events(self, test_db):
        """Test balance with mixed event types."""
        today = date.today()

        # Initial: +50
        add_ledger_event("INITIAL", "TEST_SKU_KEY_L", 50, today, db_path=test_db)

        # Sales: -10
        add_ledger_event("SALE", "TEST_SKU_KEY_L", -10, today, db_path=test_db)

        # Return: +2
        add_ledger_event("RETURN", "TEST_SKU_KEY_L", 2, today, db_path=test_db)

        # Inbound: +30
        add_ledger_event("INBOUND", "TEST_SKU_KEY_L", 30, today, db_path=test_db)

        # Adjustment: -5 (damaged goods)
        add_ledger_event("ADJUSTMENT", "TEST_SKU_KEY_L", -5, today, db_path=test_db)

        balance = get_stock_balance("TEST_SKU_KEY_L", db_path=test_db)
        assert balance == 67  # 50 - 10 + 2 + 30 - 5

    def test_negative_balance_allowed(self, test_db):
        """Test that negative balance is allowed (overselling scenario)."""
        today = date.today()

        # Initial: +10
        add_ledger_event("INITIAL", "TEST_SKU_KEY_S", 10, today, db_path=test_db)

        # Sell more than available: -15
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -15, today, db_path=test_db)

        balance = get_stock_balance("TEST_SKU_KEY_S", db_path=test_db)
        assert balance == -5  # Negative balance is allowed


class TestGetStockBalancesAll:
    """Tests for get_stock_balances_all function."""

    def test_get_all_balances(self, test_db):
        """Test retrieving balances for all SKUs."""
        today = date.today()

        # Add events for multiple SKUs
        add_ledger_event("INITIAL", "TEST_SKU_KEY_S", 20, today, db_path=test_db)
        add_ledger_event("INITIAL", "TEST_SKU_KEY_M", 30, today, db_path=test_db)
        add_ledger_event("INITIAL", "TEST_SKU_KEY_L", 40, today, db_path=test_db)

        add_ledger_event("SALE", "TEST_SKU_KEY_M", -5, today, db_path=test_db)

        balances = get_stock_balances_all(db_path=test_db)

        assert balances["TEST_SKU_KEY_S"] == 20
        assert balances["TEST_SKU_KEY_M"] == 25  # 30 - 5
        assert balances["TEST_SKU_KEY_L"] == 40


class TestRebuildSnapshot:
    """Tests for rebuild_snapshot_from_ledger function."""

    def test_rebuild_snapshot_matches_ledger(self, test_db):
        """Test snapshot rebuilding matches ledger totals."""
        today = date.today()

        # Add some events
        add_ledger_event("INITIAL", "TEST_SKU_KEY_S", 10, today, db_path=test_db)
        add_ledger_event("INITIAL", "TEST_SKU_KEY_M", 20, today, db_path=test_db)
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -3, today, db_path=test_db)

        # Rebuild snapshot
        rows_created = rebuild_snapshot_from_ledger(snapshot_date=today, db_path=test_db)

        assert rows_created == 2  # Two SKUs with events

        # Verify snapshot values match ledger
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row

        snapshot_s = conn.execute("""
            SELECT current_stock FROM fact_inventory_snapshot_size
            WHERE sku_id = 'TEST_SKU_KEY_S' AND snapshot_date = ?
        """, (today.isoformat(),)).fetchone()

        snapshot_m = conn.execute("""
            SELECT current_stock FROM fact_inventory_snapshot_size
            WHERE sku_id = 'TEST_SKU_KEY_M' AND snapshot_date = ?
        """, (today.isoformat(),)).fetchone()

        conn.close()

        assert snapshot_s["current_stock"] == 7  # 10 - 3
        assert snapshot_m["current_stock"] == 20

    def test_rebuild_includes_inbound(self, test_db):
        """Test snapshot includes pending PO inbound stock."""
        today = date.today()

        # Add initial stock
        add_ledger_event("INITIAL", "TEST_SKU_KEY_L", 50, today, db_path=test_db)

        # Add pending PO
        conn = sqlite3.connect(str(test_db))
        conn.execute("""
            INSERT INTO po_header (po_id, status)
            VALUES ('PO-2025-001', 'IN_TRANSIT')
        """)
        conn.execute("""
            INSERT INTO po_line (po_id, sku_key, sku_id, my_size, order_qty, received_qty, status, unit_cost_cny)
            VALUES ('PO-2025-001', 'TEST_SKU_KEY', 'TEST_SKU_KEY_L', 'L', 30, 0, 'PENDING', 45.0)
        """)
        conn.commit()
        conn.close()

        # Rebuild snapshot
        rebuild_snapshot_from_ledger(snapshot_date=today, db_path=test_db)

        # Verify inbound_stock is included
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        snapshot = conn.execute("""
            SELECT current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_id = 'TEST_SKU_KEY_L' AND snapshot_date = ?
        """, (today.isoformat(),)).fetchone()
        conn.close()

        assert snapshot["current_stock"] == 50
        assert snapshot["inbound_stock"] == 30


class TestEventDateVsCreatedAt:
    """Tests for event_date vs created_at behavior."""

    def test_event_date_vs_created_at(self, test_db):
        """Test that event_date can be different from created_at (backdated events)."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Add event for yesterday (backdated)
        add_ledger_event(
            event_type="SALE",
            sku_id="TEST_SKU_KEY_XL",
            qty_change=-5,
            event_date=yesterday,  # Backdated
            db_path=test_db,
        )

        # Add initial event for yesterday
        add_ledger_event(
            event_type="INITIAL",
            sku_id="TEST_SKU_KEY_XL",
            qty_change=100,
            event_date=yesterday,
            db_path=test_db,
        )

        # Balance as of yesterday should include both events
        balance_yesterday = get_stock_balance(
            "TEST_SKU_KEY_XL",
            as_of_date=yesterday,
            db_path=test_db,
        )
        assert balance_yesterday == 95  # 100 - 5

        # Add event for today
        add_ledger_event(
            event_type="SALE",
            sku_id="TEST_SKU_KEY_XL",
            qty_change=-10,
            event_date=today,
            db_path=test_db,
        )

        # Balance as of today should include all events
        balance_today = get_stock_balance(
            "TEST_SKU_KEY_XL",
            as_of_date=today,
            db_path=test_db,
        )
        assert balance_today == 85  # 100 - 5 - 10


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_count_ledger_events(self, test_db):
        """Test counting ledger events."""
        today = date.today()

        add_ledger_event("INITIAL", "TEST_SKU_KEY_S", 10, today, db_path=test_db)
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -1, today, db_path=test_db)
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -2, today, db_path=test_db)
        add_ledger_event("INITIAL", "TEST_SKU_KEY_M", 20, today, db_path=test_db)

        # Count all events
        total = count_ledger_events(db_path=test_db)
        assert total == 4

        # Count by type
        sales = count_ledger_events(event_type="SALE", db_path=test_db)
        assert sales == 2

        # Count by SKU
        sku_s = count_ledger_events(sku_id="TEST_SKU_KEY_S", db_path=test_db)
        assert sku_s == 3

    def test_get_event_summary(self, test_db):
        """Test event summary by type."""
        today = date.today()

        add_ledger_event("INITIAL", "TEST_SKU_KEY_S", 100, today, db_path=test_db)
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -10, today, db_path=test_db)
        add_ledger_event("SALE", "TEST_SKU_KEY_S", -5, today, db_path=test_db)
        add_ledger_event("RETURN", "TEST_SKU_KEY_S", 2, today, db_path=test_db)

        summary = get_event_summary(db_path=test_db)

        assert summary["INITIAL"]["count"] == 1
        assert summary["INITIAL"]["qty_total"] == 100
        assert summary["SALE"]["count"] == 2
        assert summary["SALE"]["qty_total"] == -15  # -10 + -5
        assert summary["RETURN"]["count"] == 1
        assert summary["RETURN"]["qty_total"] == 2
