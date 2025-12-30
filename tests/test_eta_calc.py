"""
TASK-180: Tests for ETA Calculation Module (Phase 10)

Tests the ETA calculation functions in core/po/eta.py.

8+ tests covering:
- Prep days estimation
- ETA calculation from different date sources
- Delay handling
- PO header updates
- Batch recalculation
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os

from core.po.eta import (
    estimate_prep_days,
    calc_eta,
    update_po_eta,
    recalc_all_etas,
    get_eta_status,
    calc_days_until_arrival,
    CARGO_TO_ALM_DAYS,
    TOTAL_CARGO_DAYS,
    SELLER_TO_CARGO_DAYS,
)


@pytest.fixture
def test_db():
    """Create a temporary database with required schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create po_header table with ETA fields
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
            alm_arrival_nom TEXT,
            ast_arrival_nom TEXT,
            weight_kg REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


class TestEstimatePrepDays:
    """Tests for estimate_prep_days function."""

    def test_estimate_prep_days_basic(self):
        """Test basic prep days calculation."""
        # 70 kg = 1 day
        assert estimate_prep_days(70) == 1
        # 140 kg = 2 days
        assert estimate_prep_days(140) == 2
        # 700 kg = 10 days
        assert estimate_prep_days(700) == 10

    def test_estimate_prep_days_fractional(self):
        """Test ceiling behavior for fractional days."""
        # 71 kg should round up to 2 days
        assert estimate_prep_days(71) == 2
        # 100 kg should be 2 days
        assert estimate_prep_days(100) == 2

    def test_estimate_prep_days_capped(self):
        """Test prep days capped at max_days."""
        # 2000 kg would be ~29 days, but capped at 20
        assert estimate_prep_days(2000) == 20
        # Custom cap
        assert estimate_prep_days(2000, max_days=10) == 10

    def test_estimate_prep_days_zero_or_negative(self):
        """Test handling of zero/negative weight."""
        assert estimate_prep_days(0) == 1
        assert estimate_prep_days(-100) == 1


class TestCalcETA:
    """Tests for calc_eta function."""

    def test_eta_from_ship_cargo(self):
        """Test ETA calculation when ship_date_cargo is known."""
        ship_date = date(2025, 1, 1)
        alm_nom, ast_nom = calc_eta(ship_date_cargo=ship_date)

        assert alm_nom == date(2025, 1, 19)  # +18 days
        assert ast_nom == date(2025, 1, 22)  # +21 days

    def test_eta_from_ship_seller(self):
        """Test ETA calculation when ship_date_seller is known."""
        ship_date = date(2025, 1, 1)
        alm_nom, ast_nom = calc_eta(ship_date_seller=ship_date)

        # Seller → cargo (2 days) + cargo → ALM (18 days) = 20 days
        assert alm_nom == date(2025, 1, 21)
        # Seller → cargo (2 days) + cargo → AST (21 days) = 23 days
        assert ast_nom == date(2025, 1, 24)

    def test_eta_from_order_date(self):
        """Test ETA estimation from order_date with weight."""
        order_date = date(2025, 1, 1)
        # 140 kg = 2 prep days
        alm_nom, ast_nom = calc_eta(order_date=order_date, weight_kg=140)

        # Prep (2) + seller→cargo (2) + cargo→ALM (18) = 22 days
        assert alm_nom == date(2025, 1, 23)
        # Prep (2) + seller→cargo (2) + cargo→AST (21) = 25 days
        assert ast_nom == date(2025, 1, 26)

    def test_eta_from_order_date_no_weight(self):
        """Test ETA from order_date without weight (default 7 day prep)."""
        order_date = date(2025, 1, 1)
        alm_nom, ast_nom = calc_eta(order_date=order_date)

        # Default prep (7) + seller→cargo (2) + cargo→ALM (18) = 27 days
        assert alm_nom == date(2025, 1, 28)
        # Default prep (7) + seller→cargo (2) + cargo→AST (21) = 30 days
        assert ast_nom == date(2025, 1, 31)

    def test_eta_with_delay(self):
        """Test ETA calculation with delay days."""
        ship_date = date(2025, 1, 1)
        alm_nom, ast_nom = calc_eta(ship_date_cargo=ship_date, delay_days=5)

        # ALM is not affected by delay
        assert alm_nom == date(2025, 1, 19)  # +18 days
        # AST is affected by delay
        assert ast_nom == date(2025, 1, 27)  # +21 + 5 days

    def test_eta_no_dates(self):
        """Test ETA returns None when no dates provided."""
        alm_nom, ast_nom = calc_eta()
        assert alm_nom is None
        assert ast_nom is None

    def test_eta_priority_cargo_over_seller(self):
        """Test ship_date_cargo takes priority over ship_date_seller."""
        cargo_date = date(2025, 1, 10)
        seller_date = date(2025, 1, 1)  # Earlier, but should be ignored

        alm_nom, ast_nom = calc_eta(
            ship_date_seller=seller_date,
            ship_date_cargo=cargo_date,
        )

        # Should use cargo date
        assert alm_nom == date(2025, 1, 28)  # cargo + 18
        assert ast_nom == date(2025, 1, 31)  # cargo + 21


class TestUpdatePOETA:
    """Tests for update_po_eta function."""

    def test_update_po_eta_from_cargo_date(self, test_db):
        """Test updating PO ETA from cargo ship date."""
        # Create PO
        conn = sqlite3.connect(str(test_db))
        conn.execute("""
            INSERT INTO po_header (po_id, supplier_code, ship_date_cargo)
            VALUES ('PO-2025-001', 'SUPP_A', '2025-01-01')
        """)
        conn.commit()
        conn.close()

        # Update ETA
        alm_nom, ast_nom = update_po_eta("PO-2025-001", db_path=test_db)

        assert alm_nom == date(2025, 1, 19)
        assert ast_nom == date(2025, 1, 22)

        # Verify DB was updated
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT alm_arrival_nom, ast_arrival_nom FROM po_header
            WHERE po_id = 'PO-2025-001'
        """).fetchone()
        conn.close()

        assert row["alm_arrival_nom"] == "2025-01-19"
        assert row["ast_arrival_nom"] == "2025-01-22"


class TestRecalcAllETAs:
    """Tests for recalc_all_etas function."""

    def test_recalc_all_etas(self, test_db):
        """Test batch recalculation of ETAs."""
        # Create multiple POs with different statuses
        conn = sqlite3.connect(str(test_db))
        conn.execute("""
            INSERT INTO po_header (po_id, supplier_code, status, order_date)
            VALUES ('PO-2025-001', 'SUPP_A', 'SENT', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO po_header (po_id, supplier_code, status, ship_date_cargo)
            VALUES ('PO-2025-002', 'SUPP_B', 'IN_TRANSIT', '2025-01-05')
        """)
        # CLOSED PO should not be updated
        conn.execute("""
            INSERT INTO po_header (po_id, supplier_code, status, ship_date_cargo)
            VALUES ('PO-2025-003', 'SUPP_A', 'CLOSED', '2025-01-01')
        """)
        conn.commit()
        conn.close()

        # Recalc ETAs
        updated = recalc_all_etas(db_path=test_db)

        assert updated == 2  # Only non-closed POs

        # Verify ETAs were set
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT ast_arrival_nom FROM po_header WHERE po_id = 'PO-2025-002'
        """).fetchone()
        assert row["ast_arrival_nom"] == "2025-01-26"  # Jan 5 + 21 days

        # CLOSED should not have been updated
        row = conn.execute("""
            SELECT ast_arrival_nom FROM po_header WHERE po_id = 'PO-2025-003'
        """).fetchone()
        assert row["ast_arrival_nom"] is None
        conn.close()


class TestETAStatus:
    """Tests for ETA status helper functions."""

    def test_get_eta_status_on_time(self):
        """Test ON_TIME status for future arrival."""
        future_date = date.today() + timedelta(days=10)
        assert get_eta_status(future_date) == "ON_TIME"

    def test_get_eta_status_due_soon(self):
        """Test DUE_SOON status for arrival within 3 days."""
        soon_date = date.today() + timedelta(days=2)
        assert get_eta_status(soon_date) == "DUE_SOON"

    def test_get_eta_status_overdue(self):
        """Test OVERDUE status for past arrival."""
        past_date = date.today() - timedelta(days=1)
        assert get_eta_status(past_date) == "OVERDUE"

    def test_calc_days_until_arrival(self):
        """Test days until arrival calculation."""
        future_date = date.today() + timedelta(days=10)
        assert calc_days_until_arrival(future_date) == 10

        past_date = date.today() - timedelta(days=5)
        assert calc_days_until_arrival(past_date) == -5
