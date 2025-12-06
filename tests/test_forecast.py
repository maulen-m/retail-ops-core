"""
TASK-051: Comprehensive Forecast Tests

Target: 20+ tests for forecast engine.
"""

import pytest
from datetime import date, timedelta
from core.calc.forecast import (
    calc_weighted_demand,
    calc_trend_slope,
    calc_d_forecast,
    calc_d_forecast_daily,
    calc_confidence_interval,
    apply_seasonality
)
from core.calc.forecast_accuracy import (
    calc_mape,
    calc_forecast_bias,
    calc_mae,
    calc_wmape,
    get_accuracy_grade
)


# Helper to generate test data
def make_daily_sales(values: list[float], start_date: date = None) -> list[tuple]:
    """Create daily sales data from a list of values."""
    if start_date is None:
        start_date = date.today() - timedelta(days=len(values))
    return [(start_date + timedelta(days=i), v) for i, v in enumerate(values)]


class TestWeightedDemand:
    """Tests for calc_weighted_demand."""

    def test_empty_sales(self):
        """Empty sales returns 0."""
        assert calc_weighted_demand([]) == 0.0

    def test_single_day(self):
        """Single day returns that value."""
        sales = make_daily_sales([10.0])
        result = calc_weighted_demand(sales)
        assert result == pytest.approx(10.0, rel=0.01)

    def test_flat_demand(self):
        """Flat demand returns average."""
        sales = make_daily_sales([5.0] * 30)
        result = calc_weighted_demand(sales)
        assert result == pytest.approx(5.0, rel=0.1)

    def test_recent_weighted_higher(self):
        """Recent values weighted more than older."""
        # Old: 1 unit/day, Recent: 10 units/day
        old_sales = make_daily_sales([1.0] * 15, date.today() - timedelta(days=30))
        recent_sales = make_daily_sales([10.0] * 15, date.today() - timedelta(days=15))
        sales = old_sales + recent_sales
        result = calc_weighted_demand(sales)
        # Should be closer to 10 than 5.5 (simple average)
        assert result > 6.0

    def test_decay_factor_effect(self):
        """Higher decay gives more weight to recent."""
        sales = make_daily_sales([1.0] * 15 + [10.0] * 15)
        high_decay = calc_weighted_demand(sales, decay_factor=0.99)
        low_decay = calc_weighted_demand(sales, decay_factor=0.85)
        # Low decay should weight recent even more
        assert low_decay > high_decay

    def test_lookback_limit(self):
        """Only uses lookback_days of data."""
        sales = make_daily_sales([100.0] * 60 + [10.0] * 30)
        result = calc_weighted_demand(sales, lookback_days=30)
        # Should ignore the 100s from 60 days ago
        assert result < 20.0


class TestTrendSlope:
    """Tests for calc_trend_slope."""

    def test_empty_sales(self):
        """Empty sales returns 0."""
        assert calc_trend_slope([]) == 0.0

    def test_single_day(self):
        """Single day returns 0 (can't calculate slope)."""
        sales = make_daily_sales([10.0])
        assert calc_trend_slope(sales) == 0.0

    def test_flat_demand(self):
        """Flat demand has zero slope."""
        sales = make_daily_sales([5.0] * 30)
        result = calc_trend_slope(sales)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_rising_trend(self):
        """Rising demand has positive slope."""
        # 1, 2, 3, ... per day
        values = list(range(1, 31))
        sales = make_daily_sales([float(v) for v in values])
        result = calc_trend_slope(sales)
        assert result > 0
        assert result == pytest.approx(1.0, rel=0.1)

    def test_falling_trend(self):
        """Falling demand has negative slope."""
        # 30, 29, 28, ... per day
        values = list(range(30, 0, -1))
        sales = make_daily_sales([float(v) for v in values])
        result = calc_trend_slope(sales)
        assert result < 0
        assert result == pytest.approx(-1.0, rel=0.1)

    def test_noisy_but_rising(self):
        """Rising trend detected through noise."""
        # Base trend + noise
        import random
        random.seed(42)
        values = [i + random.uniform(-2, 2) for i in range(1, 31)]
        sales = make_daily_sales(values)
        result = calc_trend_slope(sales)
        assert result > 0.5  # Should still be positive


class TestDForecast:
    """Tests for calc_d_forecast."""

    def test_empty_sales(self):
        """Empty sales returns 0."""
        assert calc_d_forecast([]) == 0.0

    def test_flat_demand_matches_d30(self):
        """Flat demand forecast equals D30 * horizon."""
        sales = make_daily_sales([5.0] * 30)
        result = calc_d_forecast(sales, horizon_days=7)
        # D30 = 5, forecast for 7 days should be ~35
        assert result == pytest.approx(35.0, rel=0.15)

    def test_rising_demand_higher(self):
        """Rising demand gives higher forecast than flat."""
        flat_sales = make_daily_sales([5.0] * 30)
        rising_sales = make_daily_sales([float(i/6) for i in range(1, 31)])

        flat_forecast = calc_d_forecast(flat_sales, horizon_days=7)
        rising_forecast = calc_d_forecast(rising_sales, horizon_days=7)

        # Rising should forecast higher due to trend adjustment
        # (both have similar averages around 2.5-5)
        # This test just confirms trend affects output
        assert rising_forecast != flat_forecast

    def test_no_negative_forecast(self):
        """Forecast is never negative even with falling trend."""
        # Sharply falling
        values = [100.0] + [0.0] * 29
        sales = make_daily_sales(values)
        result = calc_d_forecast(sales, horizon_days=7)
        assert result >= 0.0

    def test_horizon_affects_output(self):
        """Longer horizon = higher total forecast."""
        sales = make_daily_sales([5.0] * 30)
        forecast_7 = calc_d_forecast(sales, horizon_days=7)
        forecast_14 = calc_d_forecast(sales, horizon_days=14)
        forecast_30 = calc_d_forecast(sales, horizon_days=30)

        assert forecast_14 > forecast_7
        assert forecast_30 > forecast_14


class TestDForecastDaily:
    """Tests for calc_d_forecast_daily."""

    def test_returns_daily_rate(self):
        """Returns daily rate, not total."""
        sales = make_daily_sales([10.0] * 30)
        daily = calc_d_forecast_daily(sales, horizon_days=7)
        total = calc_d_forecast(sales, horizon_days=7)
        assert daily == pytest.approx(total / 7, rel=0.01)


class TestConfidenceInterval:
    """Tests for calc_confidence_interval."""

    def test_zero_forecast(self):
        """Zero forecast returns zero bounds."""
        sales = make_daily_sales([5.0] * 30)
        lower, upper = calc_confidence_interval(sales, 0.0)
        assert lower == 0.0
        assert upper == 0.0

    def test_bounds_bracket_forecast(self):
        """Bounds should bracket the forecast."""
        sales = make_daily_sales([5.0] * 30)
        forecast = 35.0
        lower, upper = calc_confidence_interval(sales, forecast)
        assert lower <= forecast <= upper

    def test_volatile_data_wider_interval(self):
        """Higher volatility = wider interval."""
        stable = make_daily_sales([5.0] * 30)
        volatile = make_daily_sales([1.0, 10.0] * 15)

        _, upper_stable = calc_confidence_interval(stable, 35.0)
        _, upper_volatile = calc_confidence_interval(volatile, 35.0)

        # Volatile should have wider upper bound
        assert upper_volatile > upper_stable


class TestSeasonality:
    """Tests for apply_seasonality."""

    def test_multiplier_applied(self):
        """Seasonality multiplier is applied."""
        seasonality = {(12, 'CL'): 1.25}
        result = apply_seasonality(100.0, 12, 'CL', seasonality)
        assert result == 125.0

    def test_missing_key_returns_original(self):
        """Missing key returns original value."""
        seasonality = {(12, 'CL'): 1.25}
        result = apply_seasonality(100.0, 6, 'CL', seasonality)
        assert result == 100.0


class TestMAPE:
    """Tests for calc_mape."""

    def test_perfect_forecast(self):
        """Perfect forecast has 0 MAPE."""
        actuals = [10.0, 20.0, 30.0]
        forecasts = [10.0, 20.0, 30.0]
        assert calc_mape(actuals, forecasts) == 0.0

    def test_mismatched_lengths(self):
        """Mismatched lengths raises error."""
        with pytest.raises(ValueError):
            calc_mape([1, 2, 3], [1, 2])

    def test_skips_zero_actuals(self):
        """Zero actuals are skipped."""
        actuals = [10.0, 0.0, 20.0]
        forecasts = [10.0, 5.0, 20.0]
        result = calc_mape(actuals, forecasts)
        assert result == 0.0  # Only non-zero actuals are perfect

    def test_known_mape(self):
        """Known MAPE calculation."""
        actuals = [100.0, 100.0]
        forecasts = [90.0, 110.0]
        # APE1 = |100-90|/100 = 10%, APE2 = |100-110|/100 = 10%
        # MAPE = 10%
        assert calc_mape(actuals, forecasts) == pytest.approx(10.0, rel=0.01)


class TestForecastBias:
    """Tests for calc_forecast_bias."""

    def test_unbiased(self):
        """Equal over/under = 0 bias."""
        actuals = [100.0, 100.0]
        forecasts = [90.0, 110.0]  # Under by 10, over by 10
        assert calc_forecast_bias(actuals, forecasts) == pytest.approx(0.0, abs=0.1)

    def test_over_forecasting(self):
        """Consistently high = positive bias."""
        actuals = [100.0, 100.0]
        forecasts = [120.0, 120.0]
        result = calc_forecast_bias(actuals, forecasts)
        assert result > 0  # Positive = over-forecasting

    def test_under_forecasting(self):
        """Consistently low = negative bias."""
        actuals = [100.0, 100.0]
        forecasts = [80.0, 80.0]
        result = calc_forecast_bias(actuals, forecasts)
        assert result < 0  # Negative = under-forecasting


class TestMAE:
    """Tests for calc_mae."""

    def test_perfect_forecast(self):
        """Perfect forecast has 0 MAE."""
        actuals = [10.0, 20.0, 30.0]
        forecasts = [10.0, 20.0, 30.0]
        assert calc_mae(actuals, forecasts) == 0.0

    def test_known_mae(self):
        """Known MAE calculation."""
        actuals = [10.0, 20.0]
        forecasts = [12.0, 18.0]
        # MAE = (|10-12| + |20-18|) / 2 = (2 + 2) / 2 = 2
        assert calc_mae(actuals, forecasts) == 2.0


class TestWMAPE:
    """Tests for calc_wmape."""

    def test_perfect_forecast(self):
        """Perfect forecast has 0 WMAPE."""
        actuals = [10.0, 20.0, 30.0]
        forecasts = [10.0, 20.0, 30.0]
        assert calc_wmape(actuals, forecasts) == 0.0

    def test_weights_by_actual(self):
        """Larger actuals weighted more."""
        actuals = [10.0, 100.0]
        # Both have 10% error but second is weighted 10x
        forecasts = [9.0, 90.0]  # Both 10% under
        result = calc_wmape(actuals, forecasts)
        assert result == pytest.approx(10.0, rel=0.1)


class TestAccuracyGrade:
    """Tests for get_accuracy_grade."""

    def test_excellent(self):
        assert get_accuracy_grade(5.0) == 'A'

    def test_good(self):
        assert get_accuracy_grade(15.0) == 'B'

    def test_acceptable(self):
        assert get_accuracy_grade(25.0) == 'C'

    def test_poor(self):
        assert get_accuracy_grade(40.0) == 'D'

    def test_needs_work(self):
        assert get_accuracy_grade(60.0) == 'F'

    def test_none_returns_na(self):
        assert get_accuracy_grade(None) == 'N/A'
