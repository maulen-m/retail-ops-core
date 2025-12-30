"""
TASK-179: Tests for PO Lifecycle Module (Phase 10)

Tests the PO lifecycle functions in core/po/lifecycle.py.

14 tests covering:
- PO ID generation
- PO creation (DRAFT/SENT status)
- PO line management
- Field updates with immutable field protection
- Status transitions
- PO arrival confirmation with ledger events
- PO closing
- Line receipt (partial/full)
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os

from core.po.lifecycle import (
    generate_po_id,
    create_po,
    add_po_line,
    get_po,
    get_po_lines,
    update_po_field,
    update_po_status,
    confirm_po_arrival,
    close_po,
    receive_po_line,
    PO_STATUS_FLOW,
    IMMUTABLE_FIELDS,
)


@pytest.fixture
def test_db():
    """Create a temporary database with required schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create po_header table
    conn.execute("""
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT NOT NULL,
            status TEXT DEFAULT 'DRAFT',
            order_date TEXT,
            ship_date_seller TEXT,
            ship_date_cargo TEXT,
            alm_arrival_date TEXT,
            ast_arrival_date TEXT,
            archive_alm_arrival TEXT,
            archive_ast_arrival TEXT,
            total_qty INTEGER DEFAULT 0,
            total_cost_cny REAL DEFAULT 0,
            fx_rate_cny_actual REAL,
            fx_rate_usd_kzt REAL,
            weight_kg REAL DEFAULT 0,
            notes TEXT,
            created_by TEXT DEFAULT 'system',
            closed_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
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
            unit_cost_cny REAL NOT NULL,
            status TEXT DEFAULT 'PENDING',
            FOREIGN KEY (po_id) REFERENCES po_header(po_id)
        )
    """)

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

    # Create fact_input_audit table
    conn.execute("""
        CREATE TABLE fact_input_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            change_type TEXT NOT NULL,
            source TEXT DEFAULT 'SYSTEM',
            created_at TEXT DEFAULT (datetime('now'))
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

    # Seed dim_sku_size with test data
    test_sizes = [
        ("LINE52_S", "LINE52", "S", 1),
        ("LINE52_M", "LINE52", "M", 2),
        ("LINE52_L", "LINE52", "L", 3),
        ("LINE52_XL", "LINE52", "XL", 4),
        ("LINE51_S", "LINE51", "S", 1),
        ("LINE51_M", "LINE51", "M", 2),
        ("LINE51_L", "LINE51", "L", 3),
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


class TestGeneratePOId:
    """Tests for generate_po_id function."""

    def test_generate_unique_po_id(self, test_db):
        """Test PO ID generation follows pattern PO-YYYY-NNN."""
        po_id = generate_po_id(db_path=test_db)

        year = date.today().year
        assert po_id.startswith(f"PO-{year}-")
        assert po_id == f"PO-{year}-001"

    def test_generate_sequential_po_ids(self, test_db):
        """Test sequential PO IDs are generated correctly."""
        # Create first PO
        create_po("SUPP_A", db_path=test_db)

        # Generate next ID
        po_id = generate_po_id(db_path=test_db)

        year = date.today().year
        assert po_id == f"PO-{year}-002"


class TestCreatePO:
    """Tests for create_po function."""

    def test_create_po_draft(self, test_db):
        """Test creating PO in DRAFT status."""
        po_id = create_po(
            supplier_code="SUPP_A",
            notes="Test PO",
            created_by="adil",
            db_path=test_db,
        )

        po = get_po(po_id, db_path=test_db)
        assert po is not None
        assert po["status"] == "DRAFT"
        assert po["supplier_code"] == "SUPP_A"
        assert po["notes"] == "Test PO"
        assert po["created_by"] == "adil"

    def test_create_po_with_order_date_sent_status(self, test_db):
        """Test PO with order_date is created in SENT status."""
        today = date.today()
        po_id = create_po(
            supplier_code="SUPP_B",
            order_date=today,
            db_path=test_db,
        )

        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "SENT"
        assert po["order_date"] == today.isoformat()


class TestAddPOLine:
    """Tests for add_po_line function."""

    def test_add_po_line(self, test_db):
        """Test adding a line item to a PO."""
        po_id = create_po("SUPP_A", db_path=test_db)

        line_id = add_po_line(
            po_id=po_id,
            sku_id="LINE52_M",
            order_qty=10,
            unit_cost_cny=45.0,
            db_path=test_db,
        )

        assert line_id is not None

        lines = get_po_lines(po_id, db_path=test_db)
        assert len(lines) == 1
        assert lines[0]["sku_id"] == "LINE52_M"
        assert lines[0]["sku_key"] == "LINE52"
        assert lines[0]["my_size"] == "M"
        assert lines[0]["order_qty"] == 10
        assert lines[0]["unit_cost_cny"] == 45.0
        assert lines[0]["status"] == "PENDING"

    def test_add_multiple_lines(self, test_db):
        """Test adding multiple lines to a PO."""
        po_id = create_po("SUPP_A", db_path=test_db)

        add_po_line(po_id, "LINE52_S", 5, 45.0, db_path=test_db)
        add_po_line(po_id, "LINE52_M", 10, 45.0, db_path=test_db)
        add_po_line(po_id, "LINE52_L", 8, 45.0, db_path=test_db)

        lines = get_po_lines(po_id, db_path=test_db)
        assert len(lines) == 3


class TestUpdatePOField:
    """Tests for update_po_field function."""

    def test_update_po_field(self, test_db):
        """Test updating a PO field."""
        po_id = create_po("SUPP_A", db_path=test_db)

        update_po_field(
            po_id=po_id,
            field_name="notes",
            new_value="Updated notes",
            db_path=test_db,
        )

        po = get_po(po_id, db_path=test_db)
        assert po["notes"] == "Updated notes"

    def test_update_immutable_field_first_time(self, test_db):
        """Test setting immutable field first time is allowed."""
        po_id = create_po("SUPP_A", db_path=test_db)
        today = date.today()

        # First set should work
        update_po_field(
            po_id=po_id,
            field_name="archive_alm_arrival",
            new_value=today,
            db_path=test_db,
        )

        po = get_po(po_id, db_path=test_db)
        assert po["archive_alm_arrival"] == today.isoformat()

    def test_update_immutable_field_second_time_fails(self, test_db):
        """Test updating already-set immutable field raises error."""
        po_id = create_po("SUPP_A", db_path=test_db)
        today = date.today()

        # First set
        update_po_field(po_id, "archive_alm_arrival", today, db_path=test_db)

        # Second set should fail
        with pytest.raises(ValueError) as exc_info:
            update_po_field(po_id, "archive_alm_arrival", today + timedelta(days=1), db_path=test_db)

        assert "immutable" in str(exc_info.value).lower()

    def test_update_date_field_advances_status(self, test_db):
        """Test updating date field auto-advances status."""
        po_id = create_po("SUPP_A", db_path=test_db)
        today = date.today()

        # Set order_date should advance to SENT
        update_po_field(po_id, "order_date", today, db_path=test_db)

        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "SENT"


class TestUpdatePOStatus:
    """Tests for update_po_status function."""

    def test_advance_status(self, test_db):
        """Test advancing status forward."""
        po_id = create_po("SUPP_A", db_path=test_db)

        update_po_status(po_id, "SENT", db_path=test_db)

        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "SENT"

    def test_status_backwards_fails(self, test_db):
        """Test moving status backwards raises error."""
        po_id = create_po("SUPP_A", order_date=date.today(), db_path=test_db)  # SENT status

        with pytest.raises(ValueError) as exc_info:
            update_po_status(po_id, "DRAFT", db_path=test_db)

        assert "backwards" in str(exc_info.value).lower()

    def test_invalid_status_fails(self, test_db):
        """Test invalid status raises error."""
        po_id = create_po("SUPP_A", db_path=test_db)

        with pytest.raises(ValueError) as exc_info:
            update_po_status(po_id, "INVALID_STATUS", db_path=test_db)

        assert "Invalid status" in str(exc_info.value)


class TestConfirmPOArrival:
    """Tests for confirm_po_arrival function."""

    def test_confirm_alm_arrival_creates_ledger_events(self, test_db):
        """Test ALM arrival creates INBOUND ledger events."""
        po_id = create_po("SUPP_A", db_path=test_db)
        add_po_line(po_id, "LINE52_M", 10, 45.0, db_path=test_db)
        add_po_line(po_id, "LINE52_L", 5, 45.0, db_path=test_db)

        today = date.today()
        result = confirm_po_arrival(
            po_id=po_id,
            arrival_type="ALM",
            arrival_date=today,
            db_path=test_db,
        )

        assert result["lines_updated"] == 2
        assert result["units_received"] == 15  # 10 + 5
        assert result["ledger_events"] == 2

        # Check PO status
        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "ARRIVED_ALM"
        assert po["alm_arrival_date"] == today.isoformat()

    def test_confirm_ast_arrival(self, test_db):
        """Test AST arrival updates status correctly."""
        po_id = create_po("SUPP_A", db_path=test_db)
        add_po_line(po_id, "LINE51_M", 20, 40.0, db_path=test_db)

        result = confirm_po_arrival(
            po_id=po_id,
            arrival_type="AST",
            db_path=test_db,
        )

        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "ARRIVED_AST"
        assert result["units_received"] == 20


class TestClosePO:
    """Tests for close_po function."""

    def test_close_received_po(self, test_db):
        """Test closing PO in RECEIVED status."""
        po_id = create_po("SUPP_A", db_path=test_db)
        add_po_line(po_id, "LINE52_M", 10, 45.0, db_path=test_db)

        # Move to RECEIVED status
        update_po_status(po_id, "RECEIVED", db_path=test_db)

        result = close_po(po_id, db_path=test_db)
        assert result is True

        po = get_po(po_id, db_path=test_db)
        assert po["status"] == "CLOSED"
        assert po["closed_at"] is not None

    def test_close_non_received_po_fails(self, test_db):
        """Test closing PO not in RECEIVED status raises error."""
        po_id = create_po("SUPP_A", db_path=test_db)

        with pytest.raises(ValueError) as exc_info:
            close_po(po_id, db_path=test_db)

        assert "RECEIVED" in str(exc_info.value)


class TestReceivePOLine:
    """Tests for receive_po_line function."""

    def test_receive_full_quantity(self, test_db):
        """Test receiving full order quantity."""
        po_id = create_po("SUPP_A", db_path=test_db)
        line_id = add_po_line(po_id, "LINE52_XL", 10, 45.0, db_path=test_db)

        result = receive_po_line(
            po_line_id=line_id,
            received_qty=10,
            db_path=test_db,
        )

        assert result["qty_received"] == 10
        assert result["new_total"] == 10
        assert result["status"] == "RECEIVED"
        assert result["ledger_created"] is True

    def test_receive_partial_quantity(self, test_db):
        """Test receiving partial quantity."""
        po_id = create_po("SUPP_A", db_path=test_db)
        line_id = add_po_line(po_id, "LINE51_L", 20, 40.0, db_path=test_db)

        # First receipt
        result1 = receive_po_line(line_id, 8, db_path=test_db)
        assert result1["qty_received"] == 8
        assert result1["new_total"] == 8
        assert result1["status"] == "PARTIAL"

        # Second receipt
        result2 = receive_po_line(line_id, 12, db_path=test_db)
        assert result2["qty_received"] == 12
        assert result2["new_total"] == 20
        assert result2["status"] == "RECEIVED"
