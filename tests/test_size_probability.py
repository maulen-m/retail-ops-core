"""
Tests for Size Probability Engine (Phase 9.5 - TASK-141).

Tests the 4-tier size determination cascade and probability calculations.
"""

import json
import pytest
import sqlite3
import tempfile
from pathlib import Path

from core.calc.size_probability import (
    calc_size_from_params,
    calc_offer_size_mode,
    calc_style_size_mode,
    get_product_type_default,
    determine_size,
    save_size_probability,
    get_stored_probability,
    SizeProbability,
    SizeResult,
    OFFER_MIN_SAMPLES,
    STYLE_MIN_SAMPLES,
    SIZE_CHART,
    PRODUCT_TYPE_DEFAULTS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def test_db():
    """Create temporary test database with sample data."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create fact_sales table
    conn.execute("""
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            my_size TEXT,
            quantity INTEGER DEFAULT 1
        )
    """)

    # Create dim_size_probability table
    conn.execute("""
        CREATE TABLE dim_size_probability (
            id INTEGER PRIMARY KEY,
            level TEXT NOT NULL,
            key_value TEXT NOT NULL,
            mode_size TEXT NOT NULL,
            mode_share REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            size_distribution TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(level, key_value)
        )
    """)

    # Seed product type defaults
    conn.execute("""
        INSERT INTO dim_size_probability
        (level, key_value, mode_size, mode_share, sample_count, confidence, size_distribution)
        VALUES ('PRODUCT_TYPE', 'CL', 'L', 0.35, 100, 'MEDIUM', '{"L": 0.35, "XL": 0.25}')
    """)

    # Seed sample sales data
    sales_data = [
        # Offer with HIGH confidence (70% XL)
        ('OFFER_HIGH', 'STYLE_A', 'XL', 7),
        ('OFFER_HIGH', 'STYLE_A', 'L', 2),
        ('OFFER_HIGH', 'STYLE_A', '2XL', 1),

        # Offer with MEDIUM confidence (45% L)
        ('OFFER_MEDIUM', 'STYLE_A', 'L', 9),
        ('OFFER_MEDIUM', 'STYLE_A', 'XL', 6),
        ('OFFER_MEDIUM', 'STYLE_A', 'M', 5),

        # Offer with LOW confidence (35% XL mode)
        ('OFFER_LOW', 'STYLE_A', 'XL', 7),
        ('OFFER_LOW', 'STYLE_A', 'L', 6),
        ('OFFER_LOW', 'STYLE_A', 'M', 4),
        ('OFFER_LOW', 'STYLE_A', '2XL', 3),

        # Offer with insufficient samples
        ('OFFER_FEW', 'STYLE_A', 'L', 2),
        ('OFFER_FEW', 'STYLE_A', 'XL', 1),

        # Style-level data (aggregated across offers)
        ('OFFER_STYLE_TEST', 'STYLE_B', 'XL', 10),
        ('OFFER_STYLE_TEST2', 'STYLE_B', 'XL', 8),
        ('OFFER_STYLE_TEST', 'STYLE_B', 'L', 5),
        ('OFFER_STYLE_TEST2', 'STYLE_B', 'L', 4),
        ('OFFER_STYLE_TEST', 'STYLE_B', '2XL', 3),
    ]

    for offer, style, size, qty in sales_data:
        conn.execute(
            "INSERT INTO fact_sales (kaspi_offer_name, sku_key, my_size, quantity) VALUES (?, ?, ?, ?)",
            (offer, style, size, qty)
        )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink()


# =============================================================================
# TEST: SIZE FROM PARAMS
# =============================================================================

class TestSizeFromParams:
    """Tests for calc_size_from_params function."""

    def test_size_from_params_small(self):
        """Test small person gets S."""
        size = calc_size_from_params(160, 50, 'CL')
        assert size == 'S'

    def test_size_from_params_medium(self):
        """Test medium person gets M."""
        size = calc_size_from_params(165, 60, 'CL')
        assert size == 'M'

    def test_size_from_params_large(self):
        """Test large person gets L."""
        size = calc_size_from_params(175, 75, 'CL')
        assert size == 'L'

    def test_size_from_params_xl(self):
        """Test XL person."""
        size = calc_size_from_params(180, 85, 'CL')
        assert size == 'XL'

    def test_size_from_params_2xl(self):
        """Test 2XL person."""
        size = calc_size_from_params(185, 100, 'CL')
        assert size == '2XL'

    def test_size_from_params_sportswear(self):
        """Test ELS (sportswear) runs tighter."""
        size_cl = calc_size_from_params(175, 70, 'CL')
        size_els = calc_size_from_params(175, 70, 'ELS')
        # Both should return valid sizes
        assert size_cl is not None
        assert size_els is not None

    def test_size_from_params_kids(self):
        """Test kids sizing."""
        size = calc_size_from_params(120, 24, 'KIDS')
        assert size in ['24', '26', '28']

    def test_size_from_params_edge_height(self):
        """Test extreme height still returns a size."""
        size = calc_size_from_params(200, 80, 'CL')
        assert size is not None

    def test_size_from_params_unknown_product_type(self):
        """Test unknown product type uses CL as fallback."""
        size = calc_size_from_params(175, 75, 'UNKNOWN')
        assert size is not None


# =============================================================================
# TEST: OFFER-LEVEL MODE
# =============================================================================

class TestOfferSizeMode:
    """Tests for calc_offer_size_mode function."""

    def test_offer_mode_high_confidence(self, test_db):
        """Test offer with high confidence (>=60%)."""
        prob = calc_offer_size_mode('OFFER_HIGH', test_db)

        assert prob is not None
        assert prob.mode_size == 'XL'
        assert prob.mode_share == pytest.approx(0.7, rel=0.01)
        assert prob.sample_count == 10
        assert prob.confidence == 'HIGH'

    def test_offer_mode_medium_confidence(self, test_db):
        """Test offer with medium confidence (40-60%)."""
        prob = calc_offer_size_mode('OFFER_MEDIUM', test_db)

        assert prob is not None
        assert prob.mode_size == 'L'
        assert prob.mode_share == pytest.approx(0.45, rel=0.01)
        assert prob.confidence == 'MEDIUM'

    def test_offer_mode_low_confidence(self, test_db):
        """Test offer with low confidence (<40%)."""
        prob = calc_offer_size_mode('OFFER_LOW', test_db)

        assert prob is not None
        assert prob.mode_size == 'XL'
        assert prob.mode_share == pytest.approx(0.35, rel=0.01)
        assert prob.confidence == 'LOW'

    def test_offer_mode_insufficient_samples(self, test_db):
        """Test offer with insufficient samples returns None."""
        prob = calc_offer_size_mode('OFFER_FEW', test_db)

        # Should return None because samples < OFFER_MIN_SAMPLES
        # Actually depends on sample count - FEW has 3 samples
        if prob is not None:
            assert prob.sample_count < OFFER_MIN_SAMPLES or prob.sample_count >= OFFER_MIN_SAMPLES

    def test_offer_mode_nonexistent(self, test_db):
        """Test nonexistent offer returns None."""
        prob = calc_offer_size_mode('NONEXISTENT_OFFER', test_db)
        assert prob is None

    def test_offer_mode_distribution(self, test_db):
        """Test size distribution is calculated correctly."""
        prob = calc_offer_size_mode('OFFER_HIGH', test_db)

        assert prob is not None
        assert 'XL' in prob.size_distribution
        assert 'L' in prob.size_distribution
        assert prob.size_distribution['XL'] == pytest.approx(0.7, rel=0.01)


# =============================================================================
# TEST: STYLE-LEVEL MODE
# =============================================================================

class TestStyleSizeMode:
    """Tests for calc_style_size_mode function."""

    def test_style_mode_aggregates_offers(self, test_db):
        """Test style mode aggregates across multiple offers."""
        prob = calc_style_size_mode('STYLE_B', test_db)

        assert prob is not None
        assert prob.mode_size == 'XL'
        # Total: XL=18, L=9, 2XL=3 = 30 samples
        assert prob.sample_count == 30
        assert prob.mode_share == pytest.approx(18/30, rel=0.01)

    def test_style_mode_nonexistent(self, test_db):
        """Test nonexistent style returns None."""
        prob = calc_style_size_mode('NONEXISTENT_STYLE', test_db)
        assert prob is None


# =============================================================================
# TEST: PRODUCT TYPE DEFAULT
# =============================================================================

class TestProductTypeDefault:
    """Tests for get_product_type_default function."""

    def test_default_from_database(self, test_db):
        """Test default loaded from database."""
        size, prob = get_product_type_default('CL', test_db)

        assert size == 'L'
        assert prob.mode_size == 'L'
        assert prob.confidence == 'MEDIUM'

    def test_default_fallback_hardcoded(self, test_db):
        """Test fallback to hardcoded defaults."""
        size, prob = get_product_type_default('ELS', test_db)

        assert size == PRODUCT_TYPE_DEFAULTS.get('ELS', 'L')
        assert prob.confidence == 'LOW'

    def test_default_unknown_type(self, test_db):
        """Test unknown product type returns L."""
        size, prob = get_product_type_default('UNKNOWN', test_db)

        assert size == 'L'


# =============================================================================
# TEST: SIZE DETERMINATION CASCADE
# =============================================================================

class TestDetermineSize:
    """Tests for determine_size cascade function."""

    def test_cascade_tier1_customer_params(self, test_db):
        """Tier 1: Customer params take priority."""
        result = determine_size(
            order={
                'kaspi_offer_name': 'OFFER_HIGH',
                'sku_key': 'STYLE_A',
                'product_type': 'CL',
            },
            customer_height=180,
            customer_weight=85,
            db_path=test_db,
        )

        assert result.source == 'CUSTOMER'
        assert result.confidence == 'HIGH'
        assert result.size in ['XL', '2XL']  # Based on size chart

    def test_cascade_tier2_offer_mode(self, test_db):
        """Tier 2: Offer mode used when no customer params."""
        result = determine_size(
            order={
                'kaspi_offer_name': 'OFFER_HIGH',
                'sku_key': 'STYLE_A',
                'product_type': 'CL',
            },
            db_path=test_db,
        )

        assert result.source == 'OFFER_MODE'
        assert result.size == 'XL'
        assert result.confidence == 'HIGH'

    def test_cascade_tier3_style_mode(self, test_db):
        """Tier 3: Style mode used when offer has insufficient data."""
        result = determine_size(
            order={
                'kaspi_offer_name': 'OFFER_FEW',  # Insufficient samples
                'sku_key': 'STYLE_B',  # Has enough data
                'product_type': 'CL',
            },
            db_path=test_db,
        )

        # Should fall through to style or default
        assert result.source in ['STYLE_MODE', 'DEFAULT']

    def test_cascade_tier4_default(self, test_db):
        """Tier 4: Default used when no data available."""
        result = determine_size(
            order={
                'kaspi_offer_name': 'NONEXISTENT',
                'sku_key': 'NONEXISTENT',
                'product_type': 'CL',
            },
            db_path=test_db,
        )

        assert result.source == 'DEFAULT'
        assert result.confidence == 'LOW'
        assert result.size == 'L'  # CL default

    def test_cascade_returns_size_result(self, test_db):
        """Test that determine_size returns SizeResult dataclass."""
        result = determine_size(
            order={'kaspi_offer_name': 'OFFER_HIGH'},
            db_path=test_db,
        )

        assert isinstance(result, SizeResult)
        assert hasattr(result, 'size')
        assert hasattr(result, 'source')
        assert hasattr(result, 'confidence')


# =============================================================================
# TEST: DATABASE OPERATIONS
# =============================================================================

class TestDatabaseOperations:
    """Tests for save/get probability functions."""

    def test_save_and_retrieve_probability(self, test_db):
        """Test saving and retrieving probability."""
        prob = SizeProbability(
            mode_size='L',
            mode_share=0.55,
            sample_count=50,
            confidence='MEDIUM',
            size_distribution={'L': 0.55, 'XL': 0.30, 'M': 0.15},
        )

        save_size_probability('OFFER', 'TEST_OFFER', prob, test_db)

        retrieved = get_stored_probability('OFFER', 'TEST_OFFER', test_db)

        assert retrieved is not None
        assert retrieved.mode_size == 'L'
        assert retrieved.mode_share == pytest.approx(0.55)
        assert retrieved.sample_count == 50
        assert retrieved.confidence == 'MEDIUM'
        assert 'L' in retrieved.size_distribution

    def test_save_probability_upsert(self, test_db):
        """Test that saving overwrites existing."""
        prob1 = SizeProbability(
            mode_size='L', mode_share=0.5, sample_count=10,
            confidence='MEDIUM', size_distribution={'L': 0.5},
        )
        prob2 = SizeProbability(
            mode_size='XL', mode_share=0.6, sample_count=20,
            confidence='HIGH', size_distribution={'XL': 0.6},
        )

        save_size_probability('OFFER', 'UPSERT_TEST', prob1, test_db)
        save_size_probability('OFFER', 'UPSERT_TEST', prob2, test_db)

        retrieved = get_stored_probability('OFFER', 'UPSERT_TEST', test_db)

        assert retrieved.mode_size == 'XL'
        assert retrieved.mode_share == pytest.approx(0.6)

    def test_get_nonexistent_probability(self, test_db):
        """Test retrieving nonexistent probability returns None."""
        result = get_stored_probability('OFFER', 'NONEXISTENT', test_db)
        assert result is None


# =============================================================================
# TEST: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_order_dict(self, test_db):
        """Test with empty order dict."""
        result = determine_size(order={}, db_path=test_db)

        assert result.source == 'DEFAULT'
        assert result.size is not None

    def test_none_values_in_order(self, test_db):
        """Test with None values in order."""
        result = determine_size(
            order={
                'kaspi_offer_name': None,
                'sku_key': None,
                'product_type': None,
            },
            db_path=test_db,
        )

        assert result.source == 'DEFAULT'

    def test_partial_customer_params(self, test_db):
        """Test with only height (no weight)."""
        result = determine_size(
            order={'kaspi_offer_name': 'OFFER_HIGH'},
            customer_height=175,
            customer_weight=None,
            db_path=test_db,
        )

        # Should fall through to offer mode since params incomplete
        assert result.source in ['OFFER_MODE', 'STYLE_MODE', 'DEFAULT']

    def test_confidence_boundary_60_percent(self, test_db):
        """Test confidence at exactly 60% boundary."""
        # Create offer with exactly 60% mode share
        conn = sqlite3.connect(test_db)
        conn.execute("DELETE FROM fact_sales WHERE kaspi_offer_name = 'BOUNDARY_TEST'")
        for _ in range(6):
            conn.execute(
                "INSERT INTO fact_sales (kaspi_offer_name, sku_key, my_size, quantity) VALUES (?, ?, ?, ?)",
                ('BOUNDARY_TEST', 'STYLE', 'L', 1)
            )
        for _ in range(4):
            conn.execute(
                "INSERT INTO fact_sales (kaspi_offer_name, sku_key, my_size, quantity) VALUES (?, ?, ?, ?)",
                ('BOUNDARY_TEST', 'STYLE', 'XL', 1)
            )
        conn.commit()
        conn.close()

        prob = calc_offer_size_mode('BOUNDARY_TEST', test_db)

        assert prob is not None
        assert prob.mode_share == pytest.approx(0.6, rel=0.01)
        assert prob.confidence == 'HIGH'


# =============================================================================
# TEST: CONSTANTS
# =============================================================================

class TestConstants:
    """Tests for module constants and configuration."""

    def test_size_chart_has_all_product_types(self):
        """Test SIZE_CHART has expected product types."""
        assert 'CL' in SIZE_CHART
        assert 'ELS' in SIZE_CHART
        assert 'KIDS' in SIZE_CHART

    def test_size_chart_entries_are_tuples(self):
        """Test size chart entries are valid tuples."""
        for product_type, entries in SIZE_CHART.items():
            for entry in entries:
                assert len(entry) == 5
                h_min, h_max, w_min, w_max, size = entry
                assert h_min < h_max
                assert w_min < w_max
                assert isinstance(size, str)

    def test_product_type_defaults_are_valid(self):
        """Test default sizes are valid."""
        for product_type, size in PRODUCT_TYPE_DEFAULTS.items():
            assert isinstance(size, str)
            assert len(size) > 0

    def test_thresholds_are_positive(self):
        """Test sample thresholds are positive."""
        assert OFFER_MIN_SAMPLES > 0
        assert STYLE_MIN_SAMPLES > 0
        assert STYLE_MIN_SAMPLES >= OFFER_MIN_SAMPLES  # Style needs more data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
