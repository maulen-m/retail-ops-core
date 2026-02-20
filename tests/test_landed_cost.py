"""
TASK-181: Tests for Landed Cost Module (Phase 10)

Tests the landed cost calculation functions in core/calc/landed_cost.py.

8+ tests covering:
- Supplier cost calculation
- Cargo cost calculation
- Landed cost calculation
- Weight-proportional freight share
- Required fields validation
"""

import pytest
import sqlite3
from pathlib import Path
import tempfile
import os

from core.calc.landed_cost import (
    calc_supplier_costs,
    calc_cargo_costs,
    calc_landed_costs,
    get_sku_landed_cost,
    calc_all_costs,
    get_po_cost_summary,
    CARGO_RATE_USD_PER_KG,
)


@pytest.fixture
def test_db():
    """Create a temporary database with required schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create po_header table with cost fields
    conn.execute("""
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT NOT NULL,
            status TEXT DEFAULT 'DRAFT',
            fx_rate_cny_actual REAL,
            fx_rate_usd_kzt REAL,
            weight_kg REAL DEFAULT 0,
            weight_real_kg REAL,
            total_cost_kzt_supplier REAL,
            cargo_cost_usd REAL,
            cargo_cost_kzt REAL,
            total_landed_cost_kzt REAL
        )
    """)

    # Create po_line table with cost fields
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
            unit_cost_kzt REAL,
            freight_share_kzt REAL,
            landed_cost_unit_kzt REAL,
            status TEXT DEFAULT 'PENDING',
            FOREIGN KEY (po_id) REFERENCES po_header(po_id)
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


def create_test_po(db_path, po_id="PO-2025-001", fx_cny=None, fx_usd=None, weight_kg=None):
    """Helper to create test PO."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO po_header (po_id, supplier_code, fx_rate_cny_actual, fx_rate_usd_kzt, weight_real_kg)
        VALUES (?, 'SUPP_A', ?, ?, ?)
    """, (po_id, fx_cny, fx_usd, weight_kg))
    conn.commit()
    conn.close()


def add_test_lines(db_path, po_id, lines):
    """Helper to add test lines."""
    conn = sqlite3.connect(str(db_path))
    for sku_id, qty, cost_cny in lines:
        sku_key = sku_id.rsplit("_", 1)[0] if "_" in sku_id else sku_id
        my_size = sku_id.rsplit("_", 1)[1] if "_" in sku_id else "M"
        conn.execute("""
            INSERT INTO po_line (po_id, sku_key, sku_id, my_size, order_qty, unit_cost_cny)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (po_id, sku_key, sku_id, my_size, qty, cost_cny))
    conn.commit()
    conn.close()


class TestCalcSupplierCosts:
    """Tests for calc_supplier_costs function."""

    def test_calc_supplier_costs(self, test_db):
        """Test basic supplier cost calculation."""
        # FX rate 78.5 KZT/CNY
        create_test_po(test_db, fx_cny=78.5)
        # Line: 10 units @ 45 CNY each
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_M", 10, 45.0),
        ])

        result = calc_supplier_costs("PO-2025-001", db_path=test_db)

        assert result["lines_updated"] == 1
        # 45 CNY × 78.5 = 3,532.5 KZT per unit
        # 10 units = 35,325 KZT total
        assert result["total_supplier_kzt"] == pytest.approx(35325.0)

    def test_calc_supplier_costs_multiple_lines(self, test_db):
        """Test supplier cost with multiple lines."""
        create_test_po(test_db, fx_cny=80.0)
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_S", 5, 45.0),   # 5 × 45 × 80 = 18,000
            ("LINE52_M", 10, 45.0),  # 10 × 45 × 80 = 36,000
            ("LINE52_L", 8, 50.0),   # 8 × 50 × 80 = 32,000
        ])

        result = calc_supplier_costs("PO-2025-001", db_path=test_db)

        assert result["lines_updated"] == 3
        # Total = 18,000 + 36,000 + 32,000 = 86,000
        assert result["total_supplier_kzt"] == pytest.approx(86000.0)

    def test_calc_supplier_requires_fx_rate(self, test_db):
        """Test that fx_rate_cny_actual is required."""
        create_test_po(test_db, fx_cny=None)  # No FX rate
        add_test_lines(test_db, "PO-2025-001", [("LINE52_M", 10, 45.0)])

        with pytest.raises(ValueError) as exc_info:
            calc_supplier_costs("PO-2025-001", db_path=test_db)

        assert "fx_rate_cny_actual" in str(exc_info.value)


class TestCalcCargoCosts:
    """Tests for calc_cargo_costs function."""

    def test_calc_cargo_costs(self, test_db):
        """Test basic cargo cost calculation."""
        # 100 kg @ 2.66 USD/kg = 266 USD
        # FX rate 495 KZT/USD = 131,670 KZT
        create_test_po(test_db, fx_usd=495.0, weight_kg=100.0)

        result = calc_cargo_costs("PO-2025-001", db_path=test_db)

        assert result["weight_kg"] == 100.0
        assert result["cargo_cost_usd"] == pytest.approx(266.0)
        assert result["cargo_cost_kzt"] == pytest.approx(131670.0)

    def test_calc_cargo_requires_weight(self, test_db):
        """Test that weight_real_kg is required."""
        create_test_po(test_db, fx_usd=495.0, weight_kg=None)

        with pytest.raises(ValueError) as exc_info:
            calc_cargo_costs("PO-2025-001", db_path=test_db)

        assert "weight_real_kg" in str(exc_info.value)

    def test_calc_cargo_requires_fx_rate(self, test_db):
        """Test that fx_rate_usd_kzt is required."""
        create_test_po(test_db, fx_usd=None, weight_kg=100.0)

        with pytest.raises(ValueError) as exc_info:
            calc_cargo_costs("PO-2025-001", db_path=test_db)

        assert "fx_rate_usd_kzt" in str(exc_info.value)


class TestCalcLandedCosts:
    """Tests for calc_landed_costs function."""

    def test_calc_landed_costs(self, test_db):
        """Test full landed cost calculation."""
        # Setup
        create_test_po(test_db, fx_cny=78.5, fx_usd=495.0, weight_kg=50.0)
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_M", 50, 45.0),  # Only line
        ])

        # Calculate costs in sequence
        calc_supplier_costs("PO-2025-001", db_path=test_db)
        calc_cargo_costs("PO-2025-001", db_path=test_db)

        result = calc_landed_costs("PO-2025-001", db_path=test_db)

        assert result["lines_updated"] == 1

        # Verify landed cost
        # Supplier: 50 × 45 × 78.5 = 176,625 KZT
        # Cargo: 50 × 2.66 × 495 = 65,835 KZT
        # Total landed = 176,625 + 65,835 = 242,460 KZT
        assert result["total_landed_kzt"] == pytest.approx(242460.0, rel=0.01)

    def test_freight_share_proportional_to_qty(self, test_db):
        """Test freight is split proportionally by quantity."""
        create_test_po(test_db, fx_cny=80.0, fx_usd=500.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_S", 25, 45.0),   # 25%
            ("LINE52_M", 50, 45.0),   # 50%
            ("LINE52_L", 25, 45.0),   # 25%
        ])

        calc_supplier_costs("PO-2025-001", db_path=test_db)
        calc_cargo_costs("PO-2025-001", db_path=test_db)
        calc_landed_costs("PO-2025-001", db_path=test_db)

        # Total cargo: 100 × 2.66 × 500 = 133,000 KZT
        # Verify freight shares
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row

        lines = conn.execute("""
            SELECT sku_id, freight_share_kzt FROM po_line
            WHERE po_id = 'PO-2025-001' ORDER BY sku_id
        """).fetchall()
        conn.close()

        # S and L get 25% each, M gets 50%
        assert lines[0]["freight_share_kzt"] == pytest.approx(33250.0)  # S: 25%
        assert lines[1]["freight_share_kzt"] == pytest.approx(66500.0)  # M: 50%
        assert lines[2]["freight_share_kzt"] == pytest.approx(33250.0)  # L: 25%

    def test_landed_cost_per_unit(self, test_db):
        """Test landed cost per unit calculation."""
        create_test_po(test_db, fx_cny=80.0, fx_usd=500.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_M", 100, 45.0),
        ])

        calc_supplier_costs("PO-2025-001", db_path=test_db)
        calc_cargo_costs("PO-2025-001", db_path=test_db)
        calc_landed_costs("PO-2025-001", db_path=test_db)

        # Unit cost: 45 × 80 = 3,600 KZT
        # Cargo per unit: (100 × 2.66 × 500) / 100 = 1,330 KZT
        # Landed per unit: 3,600 + 1,330 = 4,930 KZT
        landed = get_sku_landed_cost("PO-2025-001", "LINE52_M", db_path=test_db)
        assert landed == pytest.approx(4930.0)


class TestCalcLandedCostsErrors:
    """Tests for error cases."""

    def test_requires_supplier_costs_first(self, test_db):
        """Test that supplier costs must be calculated first."""
        create_test_po(test_db, fx_cny=80.0, fx_usd=500.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [("LINE52_M", 50, 45.0)])

        # Calculate cargo but not supplier
        calc_cargo_costs("PO-2025-001", db_path=test_db)

        with pytest.raises(ValueError) as exc_info:
            calc_landed_costs("PO-2025-001", db_path=test_db)

        assert "Supplier costs" in str(exc_info.value)

    def test_requires_cargo_costs_first(self, test_db):
        """Test that cargo costs must be calculated first."""
        create_test_po(test_db, fx_cny=80.0, fx_usd=500.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [("LINE52_M", 50, 45.0)])

        # Calculate supplier but not cargo
        calc_supplier_costs("PO-2025-001", db_path=test_db)

        with pytest.raises(ValueError) as exc_info:
            calc_landed_costs("PO-2025-001", db_path=test_db)

        assert "Cargo costs" in str(exc_info.value)


class TestTotalLandedMatches:
    """Tests for total consistency."""

    def test_total_landed_matches_sum(self, test_db):
        """Test that total landed equals sum of line totals."""
        create_test_po(test_db, fx_cny=78.5, fx_usd=495.0, weight_kg=200.0)
        add_test_lines(test_db, "PO-2025-001", [
            ("LINE52_S", 20, 45.0),
            ("LINE52_M", 50, 45.0),
            ("LINE52_L", 30, 48.0),
        ])

        calc_supplier_costs("PO-2025-001", db_path=test_db)
        calc_cargo_costs("PO-2025-001", db_path=test_db)
        result = calc_landed_costs("PO-2025-001", db_path=test_db)

        # Calculate sum of line totals
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        lines = conn.execute("""
            SELECT landed_cost_unit_kzt, order_qty FROM po_line
            WHERE po_id = 'PO-2025-001'
        """).fetchall()
        conn.close()

        sum_line_totals = sum(
            line["landed_cost_unit_kzt"] * line["order_qty"]
            for line in lines
        )

        assert result["total_landed_kzt"] == pytest.approx(sum_line_totals, rel=0.001)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_calc_all_costs(self, test_db):
        """Test calc_all_costs runs all calculations."""
        create_test_po(test_db, fx_cny=78.5, fx_usd=495.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [("LINE52_M", 50, 45.0)])

        result = calc_all_costs("PO-2025-001", db_path=test_db)

        assert "supplier" in result
        assert "cargo" in result
        assert "landed" in result
        assert result["landed"]["total_landed_kzt"] > 0

    def test_get_po_cost_summary(self, test_db):
        """Test cost summary retrieval."""
        create_test_po(test_db, fx_cny=78.5, fx_usd=495.0, weight_kg=100.0)
        add_test_lines(test_db, "PO-2025-001", [("LINE52_M", 50, 45.0)])

        calc_all_costs("PO-2025-001", db_path=test_db)

        summary = get_po_cost_summary("PO-2025-001", db_path=test_db)

        assert summary["supplier_cost_kzt"] is not None
        assert summary["cargo_cost_kzt"] is not None
        assert summary["total_landed_kzt"] is not None
        assert summary["fx_rate_cny"] == 78.5
        assert summary["weight_kg"] == 100.0
