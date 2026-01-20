"""
Tests for core/config/business_params.py

Covers:
- VAT effective-dated lookups (get_vat_rate)
- FX rates data (get_fx_rates, set_fx_rates)
- Demand overrides (get_demand_overrides, set_demand_override, delete_demand_override)
"""

import sqlite3
import tempfile
from datetime import date
from pathlib import Path
import pytest

from core.config.business_params import (
    get_vat_rate,
    get_fx_rates,
    set_fx_rates,
    FXRates,
    DEFAULT_FX_RATES,
    VAT_SCHEDULE,
    get_demand_overrides,
    set_demand_override,
    delete_demand_override,
)


class TestVATRate:
    """Tests for VAT rate lookup."""

    def test_vat_rate_2025_returns_3_pct(self):
        """VAT should be 3% throughout 2025."""
        assert get_vat_rate(date(2025, 1, 1)) == 0.03
        assert get_vat_rate(date(2025, 6, 15)) == 0.03
        assert get_vat_rate(date(2025, 12, 31)) == 0.03

    def test_vat_rate_2026_returns_4_pct(self):
        """VAT should be 4% from 2026-01-01."""
        assert get_vat_rate(date(2026, 1, 1)) == 0.04
        assert get_vat_rate(date(2026, 6, 15)) == 0.04
        assert get_vat_rate(date(2027, 1, 1)) == 0.04

    def test_vat_rate_boundary(self):
        """Test boundary between 3% and 4%."""
        # Last day of 3%
        assert get_vat_rate(date(2025, 12, 31)) == 0.03
        # First day of 4%
        assert get_vat_rate(date(2026, 1, 1)) == 0.04

    def test_vat_rate_none_uses_today(self):
        """None as_of_date should use today's date."""
        # Today is 2025-12-21, so should return 0.03
        rate = get_vat_rate(None)
        assert rate in (0.03, 0.04)  # Valid for any date

    def test_vat_schedule_sorted_newest_first(self):
        """VAT_SCHEDULE should be sorted newest first for lookup."""
        dates = [entry[0] for entry in VAT_SCHEDULE]
        assert dates == sorted(dates, reverse=True)


class TestFXRatesDataclass:
    """Tests for FXRates dataclass."""

    def test_fx_rates_frozen(self):
        """FXRates should be immutable (frozen)."""
        rates = FXRates(cny_kzt=78.0, usd_kzt=530.0, dlv_rate_usd_kg=2.66)
        with pytest.raises(Exception):  # FrozenInstanceError
            rates.cny_kzt = 80.0

    def test_fx_rates_to_dict(self):
        """to_dict should return correct keys."""
        rates = FXRates(cny_kzt=78.0, usd_kzt=530.0, dlv_rate_usd_kg=2.66)
        d = rates.to_dict()
        assert d == {
            "cny_kzt": 78.0,
            "usd_kzt": 530.0,
            "dlv_rate_usd_kg": 2.66,
        }

    def test_fx_rates_default_values(self):
        """Default values for effective_date and source."""
        rates = FXRates(cny_kzt=78.0, usd_kzt=530.0, dlv_rate_usd_kg=2.66)
        assert rates.effective_date is None
        assert rates.source == "FALLBACK"


class TestGetFXRates:
    """Tests for get_fx_rates function."""

    def test_get_fx_rates_returns_defaults_when_no_db(self):
        """When DB doesn't exist, return fallback defaults."""
        rates = get_fx_rates(db_path="/nonexistent/path/app.db")
        assert rates.cny_kzt == DEFAULT_FX_RATES["cny_kzt"]
        assert rates.usd_kzt == DEFAULT_FX_RATES["usd_kzt"]
        assert rates.dlv_rate_usd_kg == DEFAULT_FX_RATES["dlv_rate_usd_kg"]
        assert rates.source == "FALLBACK"

    def test_get_fx_rates_returns_defaults_when_table_missing(self):
        """When dim_fx_rates table missing, return fallback defaults."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create empty DB without dim_fx_rates table
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE dummy (id INTEGER)")
            conn.close()

            rates = get_fx_rates(db_path=db_path)
            assert rates.cny_kzt == DEFAULT_FX_RATES["cny_kzt"]
            assert rates.source == "FALLBACK"
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_fx_rates_from_db(self):
        """When DB has rates, return them."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set rates in DB
            set_fx_rates(
                cny_kzt=80.0,
                usd_kzt=540.0,
                dlv_rate_usd_kg=2.70,
                effective_date=date(2025, 1, 1),
                source="TEST",
                db_path=db_path
            )

            # Get rates back
            rates = get_fx_rates(date(2025, 6, 15), db_path=db_path)
            assert rates.cny_kzt == 80.0
            assert rates.usd_kzt == 540.0
            assert rates.dlv_rate_usd_kg == 2.70
            assert rates.effective_date == date(2025, 1, 1)
            assert rates.source == "TEST"
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_fx_rates_respects_effective_date(self):
        """Get rates effective on the specified date."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set two different rate periods
            set_fx_rates(
                cny_kzt=75.0, usd_kzt=500.0, dlv_rate_usd_kg=2.50,
                effective_date=date(2025, 1, 1), source="JAN", db_path=db_path
            )
            set_fx_rates(
                cny_kzt=80.0, usd_kzt=550.0, dlv_rate_usd_kg=2.80,
                effective_date=date(2025, 6, 1), source="JUN", db_path=db_path
            )

            # Query for date in January
            rates_jan = get_fx_rates(date(2025, 3, 15), db_path=db_path)
            assert rates_jan.cny_kzt == 75.0
            assert rates_jan.source == "JAN"

            # Query for date in June
            rates_jun = get_fx_rates(date(2025, 7, 15), db_path=db_path)
            assert rates_jun.cny_kzt == 80.0
            assert rates_jun.source == "JUN"
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_fx_rates_none_uses_today(self):
        """None as_of_date should use today's date."""
        rates = get_fx_rates(None)
        # Should return valid rates (either from DB or fallback)
        assert rates.cny_kzt > 0
        assert rates.usd_kzt > 0
        assert rates.dlv_rate_usd_kg > 0


class TestSetFXRates:
    """Tests for set_fx_rates function."""

    def test_set_fx_rates_creates_table(self):
        """set_fx_rates should create dim_fx_rates table if missing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set rates (this should create the table)
            set_fx_rates(
                cny_kzt=78.0, usd_kzt=530.0, dlv_rate_usd_kg=2.66,
                effective_date=date(2025, 1, 1), source="TEST",
                db_path=db_path
            )

            # Verify table exists
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_fx_rates'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_set_fx_rates_replaces_on_same_date(self):
        """Setting rates for same effective_date should replace."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set initial rates
            set_fx_rates(
                cny_kzt=78.0, usd_kzt=530.0, dlv_rate_usd_kg=2.66,
                effective_date=date(2025, 1, 1), source="V1",
                db_path=db_path
            )

            # Set new rates for same date
            set_fx_rates(
                cny_kzt=80.0, usd_kzt=540.0, dlv_rate_usd_kg=2.70,
                effective_date=date(2025, 1, 1), source="V2",
                db_path=db_path
            )

            # Verify only one row exists and it's the updated one
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT COUNT(*), cny_kzt, source FROM dim_fx_rates WHERE effective_date = '2025-01-01'"
            )
            count, cny_kzt, source = cursor.fetchone()
            conn.close()

            assert count == 1
            assert cny_kzt == 80.0
            assert source == "V2"
        finally:
            db_path.unlink(missing_ok=True)


class TestFXRatesIntegration:
    """Integration tests for FX rates with economics."""

    def test_default_rates_match_economics_constants(self):
        """DEFAULT_FX_RATES should match economics.py constants."""
        from core.calc.economics import CNY_KZT, FREIGHT_RATE, VOLUMETRIC_FACTOR

        # These should match (or we need to update one of them)
        assert DEFAULT_FX_RATES["cny_kzt"] == CNY_KZT
        assert DEFAULT_FX_RATES["usd_kzt"] == FREIGHT_RATE  # FREIGHT_RATE is in KZT
        assert DEFAULT_FX_RATES["dlv_rate_usd_kg"] == VOLUMETRIC_FACTOR

    def test_cogs_calculation_with_fx_rates(self):
        """Verify COGS formula using FX rates."""
        from core.calc.economics import calc_cogs

        rates = get_fx_rates()

        # COGS = base_cost_cny × cny_kzt + weight_kg × dlv_rate_usd_kg × usd_kzt
        base_cost_cny = 47  # LINE52
        weight_kg = 0.95

        expected_cogs = (
            base_cost_cny * rates.cny_kzt +
            weight_kg * rates.dlv_rate_usd_kg * rates.usd_kzt
        )
        actual_cogs = calc_cogs(base_cost_cny, weight_kg)

        # Should match within tolerance (calc_cogs uses hardcoded constants for now)
        assert abs(actual_cogs - expected_cogs) < 1  # Within 1 KZT


class TestGetDemandOverrides:
    """Tests for get_demand_overrides function."""

    def test_get_demand_overrides_returns_empty_when_no_db(self):
        """When DB doesn't exist, return empty dict."""
        overrides = get_demand_overrides(db_path="/nonexistent/path/app.db")
        assert overrides == {}

    def test_get_demand_overrides_returns_empty_when_table_missing(self):
        """When dim_demand_overrides table missing, return empty dict."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create empty DB without dim_demand_overrides table
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE dummy (id INTEGER)")
            conn.close()

            overrides = get_demand_overrides(db_path=db_path)
            assert overrides == {}
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_demand_overrides_from_db(self):
        """When DB has overrides, return them."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set overrides in DB
            set_demand_override(
                sku_key="CL_OC_MEN_LINE52_BLACK",
                d_override=50.0,
                reason="High demand SKU",
                source="TEST",
                db_path=db_path
            )
            set_demand_override(
                sku_key="CL_OC_MEN_LINE51_BLACK",
                d_override=12.0,
                reason="New product launch",
                source="TEST",
                db_path=db_path
            )

            # Get overrides back
            overrides = get_demand_overrides(db_path=db_path)
            assert overrides == {
                "CL_OC_MEN_LINE52_BLACK": 50.0,
                "CL_OC_MEN_LINE51_BLACK": 12.0,
            }
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_demand_overrides_excludes_inactive(self):
        """Inactive overrides (active_flag=0) should not be returned."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set one active, one inactive
            set_demand_override(
                sku_key="ACTIVE_SKU",
                d_override=50.0,
                active_flag=1,
                db_path=db_path
            )
            set_demand_override(
                sku_key="INACTIVE_SKU",
                d_override=30.0,
                active_flag=0,
                db_path=db_path
            )

            overrides = get_demand_overrides(db_path=db_path)
            assert "ACTIVE_SKU" in overrides
            assert "INACTIVE_SKU" not in overrides
        finally:
            db_path.unlink(missing_ok=True)


class TestSetDemandOverride:
    """Tests for set_demand_override function."""

    def test_set_demand_override_creates_table(self):
        """set_demand_override should create dim_demand_overrides table if missing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set override (this should create the table)
            set_demand_override(
                sku_key="TEST_SKU",
                d_override=25.0,
                db_path=db_path
            )

            # Verify table exists
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_demand_overrides'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_set_demand_override_replaces_on_same_window(self):
        """Setting override for same sku_key and window should replace."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Set initial override
            set_demand_override(
                sku_key="TEST_SKU",
                d_override=25.0,
                start_date="2026-01-01",
                end_date="2026-03-01",
                reason="Initial",
                db_path=db_path
            )

            # Set new override for same SKU
            set_demand_override(
                sku_key="TEST_SKU",
                d_override=50.0,
                start_date="2026-01-01",
                end_date="2026-03-01",
                reason="Updated",
                db_path=db_path
            )

            # Verify only one row exists and it's the updated one
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT COUNT(*), d_override, reason FROM dim_demand_overrides WHERE sku_key = 'TEST_SKU'"
            )
            count, d_override, reason = cursor.fetchone()
            conn.close()

            assert count == 1
            assert d_override == 50.0
            assert reason == "Updated"
        finally:
            db_path.unlink(missing_ok=True)

    def test_set_demand_override_allows_multiple_windows(self):
        """Setting overrides for different windows should create multiple rows."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            set_demand_override(
                sku_key="TEST_SKU",
                d_override=25.0,
                start_date="2026-01-01",
                end_date="2026-03-01",
                reason="Window 1",
                db_path=db_path,
            )
            set_demand_override(
                sku_key="TEST_SKU",
                d_override=30.0,
                start_date="2026-03-01",
                end_date="2026-06-01",
                reason="Window 2",
                db_path=db_path,
            )

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT COUNT(*) FROM dim_demand_overrides WHERE sku_key = 'TEST_SKU'"
            )
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 2
        finally:
            db_path.unlink(missing_ok=True)

    def test_set_demand_override_with_all_fields(self):
        """Test setting all override fields."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            set_demand_override(
                sku_key="FULL_TEST_SKU",
                d_override=75.5,
                reason="Seasonal boost",
                source="SEASONAL",
                active_flag=1,
                db_path=db_path
            )

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT sku_key, d_override, reason, source, active_flag FROM dim_demand_overrides"
            )
            row = cursor.fetchone()
            conn.close()

            assert row[0] == "FULL_TEST_SKU"
            assert row[1] == 75.5
            assert row[2] == "Seasonal boost"
            assert row[3] == "SEASONAL"
            assert row[4] == 1
        finally:
            db_path.unlink(missing_ok=True)


class TestDeleteDemandOverride:
    """Tests for delete_demand_override function."""

    def test_delete_demand_override_returns_false_when_no_db(self):
        """When DB doesn't exist, return False."""
        result = delete_demand_override("TEST_SKU", db_path="/nonexistent/path/app.db")
        assert result is False

    def test_delete_demand_override_returns_false_when_not_found(self):
        """When override doesn't exist, return False."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create table with one override
            set_demand_override(
                sku_key="EXISTING_SKU",
                d_override=25.0,
                db_path=db_path
            )

            # Try to delete non-existent SKU
            result = delete_demand_override("NONEXISTENT_SKU", db_path=db_path)
            assert result is False
        finally:
            db_path.unlink(missing_ok=True)

    def test_delete_demand_override_deletes_and_returns_true(self):
        """When override exists, delete it and return True."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create override
            set_demand_override(
                sku_key="TO_DELETE_SKU",
                d_override=25.0,
                db_path=db_path
            )

            # Verify it exists
            overrides_before = get_demand_overrides(db_path=db_path)
            assert "TO_DELETE_SKU" in overrides_before

            # Delete it
            result = delete_demand_override("TO_DELETE_SKU", db_path=db_path)
            assert result is True

            # Verify it's gone
            overrides_after = get_demand_overrides(db_path=db_path)
            assert "TO_DELETE_SKU" not in overrides_after
        finally:
            db_path.unlink(missing_ok=True)

    def test_delete_demand_override_only_deletes_specified(self):
        """Delete should only remove the specified SKU."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create two overrides
            set_demand_override(sku_key="SKU_A", d_override=25.0, db_path=db_path)
            set_demand_override(sku_key="SKU_B", d_override=30.0, db_path=db_path)

            # Delete only SKU_A
            delete_demand_override("SKU_A", db_path=db_path)

            # Verify only SKU_B remains
            overrides = get_demand_overrides(db_path=db_path)
            assert "SKU_A" not in overrides
            assert "SKU_B" in overrides
            assert overrides["SKU_B"] == 30.0
        finally:
            db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
