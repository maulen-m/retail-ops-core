"""
Tests for core/po/recommender.py

Covers the ONE PO engine:
- Order quantity calculation
- Safety stock calculation
- T_post formula (NO L in T_post!)
- Pre-arrival stock projection
- Status determination
- ROIC gate
"""

import pytest
from core.po.recommender import (
    calc_order_qty,
    calc_safety_stock,
    calc_t_post,
    calc_pre_arrival,
    calc_rop,
    should_reorder,
    calc_sku_roic,
    check_roic_gate,
    OrderStatus,
    ROICAction,
    OrderQtyResult,
)


class TestOrderQtyCalculation:
    """Tests for calc_order_qty - the main order quantity function."""

    def test_basic_order_qty(self):
        """Basic order quantity calculation."""
        result = calc_order_qty(
            d=10.0,
            current_stock=50,
            inbound_stock=0,
            ss_total=25.0,
            L=21,
            R=10,
        )
        # T_post = 10 + 25/10 = 12.5
        # Target = 10 × 12.5 = 125
        # Pre = 50 + 0 - 10×21 = 50 - 210 = 0 (clamped)
        # Order = max(0, round(125 - 0)) = 125
        assert result.order_qty == 125
        assert result.t_post == pytest.approx(12.5)
        assert result.target == pytest.approx(125.0)
        assert result.pre_arrival == pytest.approx(0.0)

    def test_t_post_does_not_include_L(self):
        """CRITICAL: T_post = R + SS/D, with NO lead time L."""
        result = calc_order_qty(
            d=10.0,
            current_stock=100,
            inbound_stock=100,
            ss_total=50.0,
            L=21,
            R=10,
        )
        # T_post should be R + SS/D = 10 + 50/10 = 15
        # NOT R + L + SS/D = 10 + 21 + 5 = 36
        assert result.t_post == pytest.approx(15.0)
        assert result.t_post < 20  # Must be less than L + R

    def test_prep_days_added_to_effective_L(self):
        """Prep days should be added to L for pre-arrival calculation."""
        result = calc_order_qty(
            d=10.0,
            current_stock=500,
            inbound_stock=0,
            ss_total=25.0,
            L=21,
            R=10,
            prep_days=5,
        )
        # effective_L = 21 + 5 = 26
        # Pre = 500 - 10×26 = 500 - 260 = 240
        assert result.effective_L == 26
        assert result.pre_arrival == pytest.approx(240.0)

    def test_order_qty_cannot_be_negative(self):
        """Order quantity should never be negative."""
        result = calc_order_qty(
            d=5.0,
            current_stock=1000,
            inbound_stock=500,
            ss_total=50.0,
            L=21,
            R=10,
        )
        assert result.order_qty >= 0

    def test_zero_demand_returns_zero_order(self):
        """Zero demand should result in zero order."""
        result = calc_order_qty(
            d=0.0,
            current_stock=100,
            inbound_stock=0,
            ss_total=25.0,
        )
        assert result.order_qty == 0
        assert result.t_post == 10  # R when D=0

    def test_status_reorder_when_total_below_rop(self):
        """Status should be REORDER when total stock < ROP."""
        result = calc_order_qty(
            d=10.0,
            current_stock=50,
            inbound_stock=50,
            ss_total=100.0,
            L=21,
        )
        # ROP = 10×21 + 100 = 310
        # Total = 50 + 50 = 100 < 310
        assert result.status == OrderStatus.REORDER

    def test_status_wait_when_inbound_covers(self):
        """Status should be WAIT when current < ROP but inbound covers."""
        result = calc_order_qty(
            d=10.0,
            current_stock=50,
            inbound_stock=300,
            ss_total=100.0,
            L=21,
        )
        # ROP = 10×21 + 100 = 310
        # Current = 50 < 310
        # Total = 350 >= 310
        assert result.status == OrderStatus.WAIT

    def test_status_ok_when_sufficient(self):
        """Status should be OK when both current and total >= ROP."""
        result = calc_order_qty(
            d=10.0,
            current_stock=400,
            inbound_stock=0,
            ss_total=100.0,
            L=21,
        )
        # ROP = 10×21 + 100 = 310
        # Current = 400 >= 310
        assert result.status == OrderStatus.OK


class TestTPostFormula:
    """Tests for T_post calculation - CRITICAL formula."""

    def test_t_post_basic(self):
        """T_post = R + SS/D"""
        t_post = calc_t_post(d=10.0, ss_total=50.0, R=10)
        # 10 + 50/10 = 15
        assert t_post == pytest.approx(15.0)

    def test_t_post_high_ss(self):
        """T_post with high safety stock."""
        t_post = calc_t_post(d=5.0, ss_total=100.0, R=10)
        # 10 + 100/5 = 30
        assert t_post == pytest.approx(30.0)

    def test_t_post_zero_demand(self):
        """T_post should return R when demand is zero."""
        t_post = calc_t_post(d=0.0, ss_total=50.0, R=10)
        assert t_post == 10.0

    def test_t_post_line52_scenario(self):
        """
        LINE52 scenario from AD-1303:
        D=42, SS=480, R=10 → T_post ≈ 21.4 (not 42.4!)
        """
        t_post = calc_t_post(d=42.0, ss_total=480.0, R=10)
        # 10 + 480/42 = 10 + 11.43 = 21.43
        assert t_post == pytest.approx(21.43, rel=0.01)
        assert t_post < 30  # Must NOT include L=21


class TestPreArrivalStock:
    """Tests for pre-arrival stock projection."""

    def test_pre_arrival_basic(self):
        """Pre = Current + Inbound - D×L"""
        pre = calc_pre_arrival(
            current_stock=100,
            inbound_stock=50,
            d=5.0,
            L=21,
        )
        # 100 + 50 - 5×21 = 150 - 105 = 45
        assert pre == pytest.approx(45.0)

    def test_pre_arrival_with_prep_days(self):
        """Prep days should extend the consumption window."""
        pre = calc_pre_arrival(
            current_stock=200,
            inbound_stock=0,
            d=5.0,
            L=21,
            prep_days=5,
        )
        # 200 - 5×26 = 200 - 130 = 70
        assert pre == pytest.approx(70.0)

    def test_pre_arrival_cannot_be_negative(self):
        """Pre-arrival should be clamped to 0."""
        pre = calc_pre_arrival(
            current_stock=50,
            inbound_stock=0,
            d=10.0,
            L=21,
        )
        # 50 - 10×21 = 50 - 210 = -160 → clamped to 0
        assert pre == 0.0


class TestSafetyStock:
    """Tests for safety stock calculation."""

    def test_ss_components(self):
        """Safety stock should have three components."""
        ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock(
            d=10.0,
            sigma=3.0,
            L=21,
            B=7,
            TV=0.15,
            z=1.65,
        )
        # ss_demand = 1.65 × 3 × sqrt(21) ≈ 22.7
        # ss_floor = 10 × 7 = 70
        # ss_mix = 0.15 × 10 × 21 = 31.5
        # ss_total = 22.7 + 70 + 31.5 = 124.2
        assert ss_demand == pytest.approx(22.7, rel=0.05)
        assert ss_floor == pytest.approx(70.0)
        assert ss_mix == pytest.approx(31.5)
        assert ss_total == pytest.approx(124.2, rel=0.05)


class TestROP:
    """Tests for reorder point calculation."""

    def test_rop_basic(self):
        """ROP = D × L + SS"""
        rop = calc_rop(d=10.0, ss_total=100.0, L=21)
        # 10 × 21 + 100 = 310
        assert rop == pytest.approx(310.0)

    def test_rop_high_demand(self):
        """ROP with high demand."""
        rop = calc_rop(d=50.0, ss_total=200.0, L=21)
        # 50 × 21 + 200 = 1250
        assert rop == pytest.approx(1250.0)


class TestShouldReorder:
    """Tests for reorder status determination."""

    def test_should_reorder_when_total_low(self):
        """REORDER when total < ROP."""
        status, reason = should_reorder(
            current_stock=50,
            inbound_stock=50,
            rop=200.0,
        )
        assert status == OrderStatus.REORDER
        assert "below ROP" in reason

    def test_wait_when_inbound_covers(self):
        """WAIT when current < ROP but total >= ROP."""
        status, reason = should_reorder(
            current_stock=50,
            inbound_stock=200,
            rop=200.0,
        )
        assert status == OrderStatus.WAIT
        assert "inbound" in reason.lower()

    def test_ok_when_sufficient(self):
        """OK when current >= ROP."""
        status, reason = should_reorder(
            current_stock=250,
            inbound_stock=0,
            rop=200.0,
        )
        assert status == OrderStatus.OK
        assert "Sufficient" in reason


class TestROICGate:
    """Tests for ROIC gate approval logic."""

    def test_roic_order_full(self):
        """ROIC >= 20% should be ORDER_FULL."""
        action, reason = check_roic_gate(0.25)  # 25%
        assert action == ROICAction.ORDER_FULL
        assert "Auto-approved" in reason

    def test_roic_order_with_flag(self):
        """ROIC 10-20% should be ORDER_WITH_FLAG."""
        action, reason = check_roic_gate(0.15)  # 15%
        assert action == ROICAction.ORDER_WITH_FLAG
        assert "review flag" in reason

    def test_roic_review_required(self):
        """ROIC < 10% should be REVIEW_REQUIRED."""
        action, reason = check_roic_gate(0.05)  # 5%
        assert action == ROICAction.REVIEW_REQUIRED
        assert "Manual review" in reason

    def test_roic_boundary_20(self):
        """ROIC = 20% exactly should be ORDER_FULL."""
        action, _ = check_roic_gate(0.20)
        assert action == ROICAction.ORDER_FULL

    def test_roic_boundary_10(self):
        """ROIC = 10% exactly should be ORDER_WITH_FLAG."""
        action, _ = check_roic_gate(0.10)
        assert action == ROICAction.ORDER_WITH_FLAG


class TestOrderQtyResult:
    """Tests for OrderQtyResult dataclass."""

    def test_deficit_property(self):
        """Deficit should be Target - Pre when positive."""
        result = calc_order_qty(
            d=10.0,
            current_stock=50,
            inbound_stock=0,
            ss_total=25.0,
        )
        assert result.deficit == result.order_qty

    def test_days_of_cover_property(self):
        """Days of cover = (Current + Inbound) / D."""
        result = calc_order_qty(
            d=10.0,
            current_stock=100,
            inbound_stock=50,
            ss_total=25.0,
        )
        # DOC = 150 / 10 = 15
        assert result.days_of_cover == pytest.approx(15.0)

    def test_days_of_cover_zero_demand(self):
        """Days of cover should be infinity when D=0."""
        result = calc_order_qty(
            d=0.0,
            current_stock=100,
            inbound_stock=0,
            ss_total=25.0,
        )
        assert result.days_of_cover == float('inf')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
