"""
Tests for PO Dashboard invariants and requirements.

INVARIANTS:
- sum(size_share) == 1 for every sized SKU
- sum(d_size) == d_sku for every sized SKU
- po_qty_total == sum(size_orders) for every SKU

REQUIREMENTS:
- LINE52 (CL_OC_MEN_LINE52_BLACK): D = 30 (2026-01-01 → 2026-03-01) or D = 30 (2026-03-01 → 2026-06-01)
- LINE51 (CL_OC_MEN_LINE51_WHITE): D = 12
- Model B: all CL SKUs have same prep_days, all ELS have prep_days=1
- Model C (default): prep_days <= R_days
"""

import json
from datetime import date
from math import ceil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
JSON_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


@pytest.fixture
def dashboard_data():
    """Load dashboard data from JSON file."""
    if not JSON_PATH.exists():
        pytest.skip("po_dashboard_data.json not found - run generate_po_dashboard_data.py first")
    with open(JSON_PATH) as f:
        return json.load(f)


class TestDemandOverrides:
    """Tests for demand override requirements."""

    @staticmethod
    def _expected_line52_override(as_of: date) -> float | None:
        if date(2026, 1, 1) <= as_of < date(2026, 3, 1):
            return 30.0
        if date(2026, 3, 1) <= as_of < date(2026, 6, 1):
            return 30.0
        return None

    @staticmethod
    def _expected_line51_override(as_of: date) -> float | None:
        if date(2026, 1, 1) <= as_of < date(2026, 3, 1):
            return 12.0
        return None

    def test_line52_demand_override(self, dashboard_data):
        """LINE52 must have the correct time-boxed d_sku."""
        po4 = dashboard_data['pos']['PLAN-0']
        line52 = None
        for sku in po4['sku_level']:
            if sku['sku_key'] == 'CL_OC_MEN_LINE52_BLACK':
                line52 = sku
                break

        assert line52 is not None, "LINE52 not found in PLAN-0 sku_level"
        cutoff_raw = dashboard_data.get("cutoff_date")
        if not cutoff_raw:
            pytest.skip("cutoff_date missing from dashboard data")
        expected = self._expected_line52_override(date.fromisoformat(cutoff_raw))
        if expected is None:
            pytest.skip("LINE52 override not required for this cutoff date")
        assert abs(line52['d_sku'] - expected) < 0.01, f"LINE52 d_sku={line52['d_sku']}, expected={expected}"
        assert 'D_OVERRIDE' in line52.get('notes', ''), "LINE52 missing D_OVERRIDE note"

    def test_line51_demand_override(self, dashboard_data):
        """LINE51 must have d_sku=12."""
        po4 = dashboard_data['pos']['PLAN-0']
        line51 = None
        for sku in po4['sku_level']:
            if sku['sku_key'] == 'CL_OC_MEN_LINE51_WHITE':
                line51 = sku
                break

        assert line51 is not None, "LINE51 not found in PLAN-0 sku_level"
        cutoff_raw = dashboard_data.get("cutoff_date")
        if not cutoff_raw:
            pytest.skip("cutoff_date missing from dashboard data")
        expected = self._expected_line51_override(date.fromisoformat(cutoff_raw))
        if expected is None:
            pytest.skip("LINE51 override not required for this cutoff date")
        assert abs(line51['d_sku'] - expected) < 0.01, f"LINE51 d_sku={line51['d_sku']}, expected={expected}"
        assert 'D_OVERRIDE' in line51.get('notes', ''), "LINE51 missing D_OVERRIDE note"


class TestPrepModelB:
    """Tests for Model B prep days requirements."""

    def test_all_cl_skus_same_prep_days_po4(self, dashboard_data):
        """All CL SKUs in PLAN-0 should have same prep_days."""
        po4 = dashboard_data['pos']['PLAN-0']
        cl_prep_days = set()

        for sku in po4['sku_level']:
            sku_key = sku.get('sku_key', '')
            prep = sku.get('prep_days', 0)
            qty = sku.get('po_qty_total', 0)

            if qty == 0:
                continue  # Skip SKUs with no order

            if sku_key.startswith('CL_'):
                cl_prep_days.add(prep)

        assert len(cl_prep_days) <= 1, f"PLAN-0 CL SKUs have inconsistent prep_days: {cl_prep_days}"

    def test_all_els_skus_prep_1(self, dashboard_data):
        """All ELS SKUs should have prep_days=1."""
        for po_name, po_data in dashboard_data['pos'].items():
            if not isinstance(po_data, dict):
                continue

            for sku in po_data.get('sku_level', []):
                sku_key = sku.get('sku_key', '')
                prep = sku.get('prep_days', 0)
                qty = sku.get('po_qty_total', 0)

                if qty == 0:
                    continue

                if sku_key.startswith('ELS_'):
                    assert prep == 1, f"{po_name} {sku_key} ELS prep_days={prep}, expected=1"

    def test_prep_days_reasonable(self, dashboard_data):
        """Verify Model B prep_days is reasonable for the weight."""
        po4 = dashboard_data['pos']['PLAN-0']

        # Calculate total CL weight and get prep_days
        total_cl_weight = 0.0
        cl_prep_days_value = None

        for sku in po4['sku_level']:
            sku_key = sku.get('sku_key', '')
            qty = sku.get('po_qty_total', 0)
            weight_kg = sku.get('po_weight_kg', 0)

            if qty == 0:
                continue

            if sku_key.startswith('CL_'):
                total_cl_weight += weight_kg
                if cl_prep_days_value is None:
                    cl_prep_days_value = sku.get('prep_days', 0)

        if total_cl_weight > 0 and cl_prep_days_value is not None:
            # Note: prep_days is calculated via convergence loop with estimated weights,
            # which may differ from final output weights. The key invariant is:
            # - prep_days should be > 1 for significant weights
            # - prep_days should be consistent across all CL SKUs (tested separately)
            assert cl_prep_days_value >= 1, "prep_days should be at least 1"
            # For ~1000+ kg, expect at least 10 prep days
            if total_cl_weight > 1000:
                assert cl_prep_days_value >= 10, \
                    f"For {total_cl_weight:.0f}kg, prep_days={cl_prep_days_value} seems too low"


class TestNoSilentSkipping:
    """Tests for no silent skipping policy."""

    def test_skus_accounted_for(self, dashboard_data):
        """Every SKU should appear in sku_level or skipped_skus."""
        po4 = dashboard_data['pos']['PLAN-0']

        sku_level_count = len(po4.get('sku_level', []))
        skipped_count = len(po4.get('skipped_skus', []))
        total_accounted = sku_level_count + skipped_count

        expected_total = dashboard_data.get('summary', {}).get('total_skus')
        if expected_total is None:
            pytest.skip("dashboard summary missing total_skus")

        # All active SKUs should be accounted for between sku_level + skipped_skus
        assert total_accounted >= expected_total, (
            f"Only {total_accounted} SKUs accounted for (expected >= {expected_total})"
        )

    def test_line52_not_silently_skipped(self, dashboard_data):
        """LINE52 must appear somewhere in the output."""
        po4 = dashboard_data['pos']['PLAN-0']

        # Check sku_level
        found_in_sku_level = any(
            s['sku_key'] == 'CL_OC_MEN_LINE52_BLACK'
            for s in po4.get('sku_level', [])
        )

        # Check skipped_skus
        skipped = po4.get('skipped_skus', [])
        found_in_skipped = False
        if isinstance(skipped, list):
            found_in_skipped = any(
                (isinstance(s, dict) and s.get('sku_key') == 'CL_OC_MEN_LINE52_BLACK') or
                (isinstance(s, str) and s == 'CL_OC_MEN_LINE52_BLACK')
                for s in skipped
            )

        assert found_in_sku_level or found_in_skipped, "LINE52 not found anywhere - silently skipped!"


class TestReconciliationInvariants:
    """Tests for size-share and d_size reconciliation invariants."""

    def test_sum_d_size_equals_d_sku(self, dashboard_data):
        """
        INVARIANT: sum(d_size) == d_sku for every sized SKU.
        This ensures demand is properly distributed across sizes.
        Note: Unsized products (ELS_PRINTER_*) are excluded - they have no size_level entries.
        """
        po4 = dashboard_data['pos']['PLAN-0']
        failures = []

        for sku in po4['sku_level']:
            sku_key = sku['sku_key']
            d_sku = sku['d_sku']

            # Skip zero-demand SKUs
            if d_sku == 0:
                continue

            # Skip unsized products (ELS_PRINTER_* are Epson printers with no sizes)
            if sku_key.startswith('ELS_PRINTER_'):
                continue

            # Get all size-level entries for this SKU
            sizes = [s for s in po4['size_level'] if s['sku_key'] == sku_key]

            # Skip if no size-level entries (unsized product)
            if not sizes:
                continue

            sum_d_size = sum(s['d_size'] for s in sizes)

            # Allow small floating point tolerance
            gap = abs(d_sku - sum_d_size)
            if gap > 0.01:
                failures.append(f"{sku_key}: d_sku={d_sku:.4f}, sum(d_size)={sum_d_size:.4f}, gap={gap:.6f}")

        assert not failures, f"sum(d_size) != d_sku for {len(failures)} SKUs:\n" + "\n".join(failures[:5])

    def test_order_qty_consistency(self, dashboard_data):
        """
        INVARIANT: po_qty_total == sum(size_orders) for every SKU.
        This ensures order totals match the sum of size allocations.
        """
        po4 = dashboard_data['pos']['PLAN-0']
        failures = []

        for sku in po4['sku_level']:
            sku_key = sku['sku_key']
            po_qty_total = sku['po_qty_total']
            size_orders = sku.get('size_orders', {})
            sum_size_orders = sum(size_orders.values())

            if po_qty_total != sum_size_orders:
                failures.append(f"{sku_key}: po_qty_total={po_qty_total}, sum(size_orders)={sum_size_orders}")

        assert not failures, f"po_qty_total != sum(size_orders) for {len(failures)} SKUs:\n" + "\n".join(failures[:5])

    def test_size_level_order_matches_sku_level(self, dashboard_data):
        """
        INVARIANT: sum of order_qty in size_level == po_qty_total in sku_level.
        """
        po4 = dashboard_data['pos']['PLAN-0']
        failures = []

        for sku in po4['sku_level']:
            sku_key = sku['sku_key']
            po_qty_total = sku['po_qty_total']

            # Get all size-level entries for this SKU
            sizes = [s for s in po4['size_level'] if s['sku_key'] == sku_key]
            sum_size_order = sum(s['order_qty'] for s in sizes)

            if po_qty_total != sum_size_order:
                failures.append(f"{sku_key}: po_qty_total={po_qty_total}, sum(size_level.order_qty)={sum_size_order}")

        assert not failures, f"size_level order mismatch for {len(failures)} SKUs:\n" + "\n".join(failures[:5])


class TestModelCPrepCap:
    """Tests for Model C capacity-capped prep days."""

    def test_prep_days_capped_at_r(self, dashboard_data):
        """
        Model C: prep_days <= R_days for all CL SKUs.
        """
        po4 = dashboard_data['pos']['PLAN-0']
        prep_model = po4.get('prep_model', 'C')
        r_days = po4.get('reorder_cycle_R', 10)

        # Only test if Model C is active
        if prep_model != 'C':
            pytest.skip(f"Model C not active (current: {prep_model})")

        violations = []
        for sku in po4['sku_level']:
            sku_key = sku['sku_key']
            prep_days = sku['prep_days']

            # Only check CL SKUs with orders
            if sku['po_qty_total'] == 0:
                continue

            # ELS product types should have prep=1
            # CL product types should have prep <= R
            if sku_key.startswith('CL_') or not sku_key.startswith('ELS_'):
                # Check for ELS product_type via prep_days (ELS = 1)
                # For CL, prep should be <= R
                if prep_days > r_days and prep_days != 1:  # Allow prep=1 for ELS
                    violations.append(f"{sku_key}: prep_days={prep_days} > R={r_days}")

        assert not violations, f"Model C violations:\n" + "\n".join(violations[:5])

    def test_prep_model_info_in_output(self, dashboard_data):
        """Verify prep model info is included in output."""
        po4 = dashboard_data['pos']['PLAN-0']

        assert 'prep_model' in po4, "prep_model not in output"
        assert po4['prep_model'] in ('B', 'C'), f"Invalid prep_model: {po4['prep_model']}"

        assert 'prep_days_clothes' in po4, "prep_days_clothes not in output"
        assert po4['prep_days_clothes'] >= 1, "prep_days_clothes should be >= 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
