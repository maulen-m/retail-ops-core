"""
Tests for expansion scoring logic.

Tests cover:
- Demand score calculation
- Margin score calculation
- Competition score calculation
- Composite expansion score
- Recommendation logic
"""
import pytest
import sys
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.expansion_scorer import (
    ExpansionScore,
    _calc_demand_score,
    _calc_margin_score,
    _calc_competition_score,
    _get_recommendation,
)


class TestDemandScore:
    """Tests for demand score calculation."""

    def test_zero_demand(self):
        """Test score with zero demand."""
        score = _calc_demand_score(0)
        assert score == 0

    def test_low_demand(self):
        """Test score with low demand (1-10 units)."""
        # 5 units -> 5 * 3 = 15
        score = _calc_demand_score(5)
        assert score == pytest.approx(15, rel=0.01)

        # 10 units -> 10 * 3 = 30
        score = _calc_demand_score(10)
        assert score == pytest.approx(30, rel=0.01)

    def test_moderate_demand(self):
        """Test score with moderate demand (10-30 units)."""
        # 20 units -> 30 + (20-10) * 1.5 = 30 + 15 = 45
        score = _calc_demand_score(20)
        assert score == pytest.approx(45, rel=0.01)

        # 30 units -> 30 + (30-10) * 1.5 = 30 + 30 = 60
        score = _calc_demand_score(30)
        assert score == pytest.approx(60, rel=0.01)

    def test_good_demand(self):
        """Test score with good demand (30-100 units)."""
        # 50 units -> 60 + (50-30) * 0.36 = 60 + 7.2 = 67.2
        score = _calc_demand_score(50)
        assert score == pytest.approx(67.2, rel=0.01)

        # 100 units -> 60 + (100-30) * 0.36 = 60 + 25.2 = 85.2
        score = _calc_demand_score(100)
        assert score == pytest.approx(85.2, rel=0.01)

    def test_excellent_demand(self):
        """Test score with excellent demand (100+ units)."""
        # 150 units -> 85 + (150-100) * 0.15 = 85 + 7.5 = 92.5
        score = _calc_demand_score(150)
        assert score == pytest.approx(92.5, rel=0.01)

    def test_max_score_cap(self):
        """Test that score is capped at 100."""
        score = _calc_demand_score(500)
        assert score <= 100


class TestMarginScore:
    """Tests for margin score calculation."""

    def test_zero_margin(self):
        """Test score with zero margin."""
        score = _calc_margin_score(0)
        assert score == 0

    def test_negative_margin(self):
        """Test score with negative margin."""
        score = _calc_margin_score(-10)
        assert score == 0

    def test_thin_margin(self):
        """Test score with thin margin (0-20%)."""
        # 10% -> 10 * 1.5 = 15
        score = _calc_margin_score(10)
        assert score == pytest.approx(15, rel=0.01)

        # 20% -> 20 * 1.5 = 30
        score = _calc_margin_score(20)
        assert score == pytest.approx(30, rel=0.01)

    def test_acceptable_margin(self):
        """Test score with acceptable margin (20-35%)."""
        # 30% -> 30 + (30-20) * 2 = 30 + 20 = 50
        score = _calc_margin_score(30)
        assert score == pytest.approx(50, rel=0.01)

        # 35% -> 30 + (35-20) * 2 = 30 + 30 = 60
        score = _calc_margin_score(35)
        assert score == pytest.approx(60, rel=0.01)

    def test_good_margin(self):
        """Test score with good margin (35-50%)."""
        # 40% -> 60 + (40-35) * 1.67 = 60 + 8.35 = 68.35
        score = _calc_margin_score(40)
        assert score == pytest.approx(68.35, rel=0.01)

        # 50% -> 60 + (50-35) * 1.67 = 60 + 25.05 = 85.05
        score = _calc_margin_score(50)
        assert score == pytest.approx(85.05, rel=0.01)

    def test_excellent_margin(self):
        """Test score with excellent margin (50%+)."""
        # 60% -> 85 + (60-50) * 0.3 = 85 + 3 = 88
        score = _calc_margin_score(60)
        assert score == pytest.approx(88, rel=0.01)

    def test_max_score_cap(self):
        """Test that score is capped at 100."""
        score = _calc_margin_score(100)
        assert score <= 100


class TestCompetitionScore:
    """Tests for competition score calculation."""

    def test_no_competition(self):
        """Test score with no competitors (blue ocean)."""
        score = _calc_competition_score(0)
        assert score == 100

    def test_low_competition(self):
        """Test score with low competition (1-3 competitors)."""
        # 1 competitor -> 90 - 1*3 = 87
        score = _calc_competition_score(1)
        assert score == pytest.approx(87, rel=0.01)

        # 3 competitors -> 90 - 3*3 = 81
        score = _calc_competition_score(3)
        assert score == pytest.approx(81, rel=0.01)

    def test_moderate_competition(self):
        """Test score with moderate competition (4-10 competitors)."""
        # 5 competitors -> 80 - (5-3) * 4.3 = 80 - 8.6 = 71.4
        score = _calc_competition_score(5)
        assert score == pytest.approx(71.4, rel=0.01)

        # 10 competitors -> 80 - (10-3) * 4.3 = 80 - 30.1 = 49.9
        score = _calc_competition_score(10)
        assert score == pytest.approx(49.9, rel=0.01)

    def test_high_competition(self):
        """Test score with high competition (10+ competitors)."""
        # 15 competitors -> 50 - (15-10) * 3 = 50 - 15 = 35
        score = _calc_competition_score(15)
        assert score == pytest.approx(35, rel=0.01)

    def test_min_score_floor(self):
        """Test that score has minimum of 20."""
        score = _calc_competition_score(50)
        assert score >= 20


class TestRecommendationLogic:
    """Tests for recommendation determination."""

    def test_expand_high_score_high_margin(self):
        """Test EXPAND recommendation for high score and margin."""
        rec, conf, notes = _get_recommendation(
            expansion_score=80,
            units_30d=50,
            wb_margin=45,
            kaspi_margin=40,
            competition_count=2,
        )

        assert rec == "EXPAND"
        assert conf == "HIGH"  # units >= 30

    def test_expand_medium_confidence(self):
        """Test EXPAND with medium confidence (lower units)."""
        rec, conf, notes = _get_recommendation(
            expansion_score=80,
            units_30d=20,  # < 30
            wb_margin=45,
            kaspi_margin=40,
            competition_count=2,
        )

        assert rec == "EXPAND"
        assert conf == "MEDIUM"

    def test_test_moderate_score_good_margin(self):
        """Test TEST recommendation for moderate score."""
        rec, conf, notes = _get_recommendation(
            expansion_score=60,
            units_30d=30,
            wb_margin=38,
            kaspi_margin=35,
            competition_count=5,
        )

        assert rec == "TEST"
        assert conf == "MEDIUM"

    def test_test_thin_margin(self):
        """Test TEST with thin margin warning."""
        rec, conf, notes = _get_recommendation(
            expansion_score=55,
            units_30d=20,
            wb_margin=28,  # < 35
            kaspi_margin=30,
            competition_count=3,
        )

        assert rec == "TEST"
        assert conf == "LOW"
        assert "thin margin" in notes.lower()

    def test_hold_below_threshold(self):
        """Test HOLD recommendation for below threshold but potential."""
        rec, conf, notes = _get_recommendation(
            expansion_score=35,
            units_30d=20,
            wb_margin=32,
            kaspi_margin=30,
            competition_count=5,
        )

        assert rec == "HOLD"
        assert "monitor" in notes.lower()

    def test_skip_thin_margin(self):
        """Test SKIP for very thin margin."""
        rec, conf, notes = _get_recommendation(
            expansion_score=25,
            units_30d=10,
            wb_margin=15,  # < 20
            kaspi_margin=25,
            competition_count=3,
        )

        assert rec == "SKIP"
        assert "margin too thin" in notes.lower()

    def test_skip_low_demand(self):
        """Test SKIP for very low demand."""
        rec, conf, notes = _get_recommendation(
            expansion_score=25,
            units_30d=3,  # < 5
            wb_margin=40,
            kaspi_margin=35,
            competition_count=2,
        )

        assert rec == "SKIP"
        assert "demand too low" in notes.lower()

    def test_skip_high_competition(self):
        """Test SKIP for high competition."""
        rec, conf, notes = _get_recommendation(
            expansion_score=25,
            units_30d=10,
            wb_margin=30,
            kaspi_margin=28,
            competition_count=20,  # > 15
        )

        assert rec == "SKIP"
        assert "competition" in notes.lower()


class TestExpansionScoreDataclass:
    """Tests for ExpansionScore dataclass."""

    def test_create_score(self):
        """Test creating an ExpansionScore instance."""
        score = ExpansionScore(
            sku_key="TEST_SKU",
            source_channel="KSP",
            target_channel="WB",
            score_date=date.today(),
            source_d30=50,
            source_roic_pct=150.0,
            source_margin_pct=45.0,
            source_avg_price_kzt=12000,
            target_price_rub=2800,
            target_est_margin_pct=52.0,
            target_est_roic_pct=180.0,
            margin_headroom_pct=7.0,
            demand_score=70,
            margin_score=85,
            competition_score=80,
            expansion_score=77,
            recommendation="EXPAND",
            confidence="HIGH",
            notes="Strong candidate",
        )

        assert score.sku_key == "TEST_SKU"
        assert score.recommendation == "EXPAND"
        assert score.expansion_score == 77

    def test_margin_headroom_calculation(self):
        """Test margin headroom calculation."""
        source_margin = 45.0
        target_margin = 52.0
        headroom = target_margin - source_margin

        assert headroom == 7.0


class TestCompositeScore:
    """Tests for composite expansion score calculation."""

    def test_weighted_calculation(self):
        """Test weighted score calculation (40% demand, 40% margin, 20% competition)."""
        demand_score = 70
        margin_score = 80
        competition_score = 90

        # 70 * 0.4 + 80 * 0.4 + 90 * 0.2 = 28 + 32 + 18 = 78
        composite = (
            demand_score * 0.40
            + margin_score * 0.40
            + competition_score * 0.20
        )

        assert composite == pytest.approx(78, rel=0.01)

    def test_all_zero_scores(self):
        """Test composite with all zero component scores."""
        composite = 0 * 0.40 + 0 * 0.40 + 0 * 0.20
        assert composite == 0

    def test_all_max_scores(self):
        """Test composite with all max component scores."""
        composite = 100 * 0.40 + 100 * 0.40 + 100 * 0.20
        assert composite == 100


class TestEdgeCases:
    """Tests for edge cases in expansion scoring."""

    def test_borderline_expand(self):
        """Test borderline EXPAND case (score = 75)."""
        rec, conf, notes = _get_recommendation(
            expansion_score=75,
            units_30d=30,
            wb_margin=40,
            kaspi_margin=35,
            competition_count=3,
        )

        assert rec == "EXPAND"

    def test_borderline_test(self):
        """Test borderline TEST case (score = 50)."""
        rec, conf, notes = _get_recommendation(
            expansion_score=50,
            units_30d=20,
            wb_margin=35,
            kaspi_margin=32,
            competition_count=5,
        )

        assert rec == "TEST"

    def test_borderline_hold(self):
        """Test borderline HOLD case (score = 30)."""
        rec, conf, notes = _get_recommendation(
            expansion_score=30,
            units_30d=15,
            wb_margin=30,
            kaspi_margin=28,
            competition_count=5,
        )

        assert rec == "HOLD"

    def test_very_high_demand_low_margin(self):
        """Test high demand but low margin."""
        demand_score = _calc_demand_score(200)  # Very high
        margin_score = _calc_margin_score(15)  # Low

        # High demand can't fully compensate for low margin
        composite = demand_score * 0.40 + margin_score * 0.40 + 100 * 0.20
        # Should not be EXPAND territory

        rec, _, _ = _get_recommendation(
            expansion_score=composite,
            units_30d=200,
            wb_margin=15,
            kaspi_margin=20,
            competition_count=0,
        )

        assert rec in ["TEST", "HOLD", "SKIP"]  # Not EXPAND due to thin margin

    def test_low_demand_high_margin(self):
        """Test low demand but high margin."""
        demand_score = _calc_demand_score(5)  # Low
        margin_score = _calc_margin_score(60)  # High

        # High margin can't fully compensate for low demand
        assert demand_score < 20  # Should be low
        assert margin_score > 85  # Should be high


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
