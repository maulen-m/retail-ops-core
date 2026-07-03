from core.cashflow.refund_reserve import compute_refund_reserve_series, apply_refund_reserve


def test_refund_reserve_series_and_apply():
    rows = [
        {
            "date": "2026-01-01",
            "cash_open": 0.0,
            "cash_flow_kzt": 100.0,
            "cash_close": 100.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 100.0,
        },
        {
            "date": "2026-01-02",
            "cash_open": 100.0,
            "cash_flow_kzt": 0.0,
            "cash_close": 100.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 200.0,
        },
        {
            "date": "2026-01-03",
            "cash_open": 100.0,
            "cash_flow_kzt": 0.0,
            "cash_close": 100.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 0.0,
        },
    ]

    series = compute_refund_reserve_series(rows, reserve_rate=0.1, window_days=2)
    assert series["2026-01-01"]["reserve_kzt"] == 10.0
    assert series["2026-01-02"]["reserve_kzt"] == 30.0
    assert series["2026-01-03"]["reserve_kzt"] == 20.0
    assert series["2026-01-02"]["delta_kzt"] == 20.0
    assert series["2026-01-03"]["delta_kzt"] == -10.0

    updated = apply_refund_reserve(rows, series)
    assert updated[0]["cash_close"] == 90.0
    assert updated[1]["cash_open"] == 90.0
    assert updated[1]["cash_close"] == 70.0
    assert updated[2]["cash_open"] == 70.0
    assert updated[2]["cash_close"] == 80.0


def test_refund_reserve_reset_date_uses_anchor_cash_and_full_reserve():
    rows = [
        {
            "date": "2026-01-01",
            "cash_open": 0.0,
            "cash_flow_kzt": 100.0,
            "cash_close": 100.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 100.0,
        },
        {
            "date": "2026-01-02",
            "cash_open": 1000.0,
            "cash_flow_kzt": 0.0,
            "cash_close": 1000.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 200.0,
        },
    ]

    series = compute_refund_reserve_series(rows, reserve_rate=0.1, window_days=2)
    updated = apply_refund_reserve(rows, series, reset_dates={"2026-01-02"})

    assert series["2026-01-02"]["reserve_kzt"] == 30.0
    assert series["2026-01-02"]["delta_kzt"] == 20.0
    assert updated[1]["cash_open"] == 1000.0
    assert updated[1]["cash_flow_kzt"] == -30.0
    assert updated[1]["cash_close"] == 970.0
