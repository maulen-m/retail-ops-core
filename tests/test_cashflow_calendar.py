from datetime import date

from scripts.rebuild_cashflow_calendar import compute_daily_rows


def test_cashflow_rollforward_identity():
    events = [
        {"event_date": "2026-01-01", "event_type": "CASH_IN", "account": "KASPI_PAY_UNIVERSAL", "amount_kzt": 1000.0},
        {"event_date": "2026-01-01", "event_type": "PO_PAYMENT", "account": "CASH", "amount_kzt": -400.0},
        {"event_date": "2026-01-02", "event_type": "COGS_RECOGNIZED", "account": "INVENTORY_ON_DELIVERY_COST", "amount_kzt": -300.0},
    ]
    rows = compute_daily_rows(events, date(2026, 1, 1), date(2026, 1, 2), run_id="test")
    assert len(rows) == 2
    day1 = rows[0]
    day2 = rows[1]

    assert day1["cash_close"] == day1["cash_open"] + day1["cash_flow_kzt"]
    assert day2["cash_close"] == day2["cash_open"] + day2["cash_flow_kzt"]
    assert day2["receivables_close"] == day2["receivables_open"] + day2["receivables_flow_kzt"]
    assert day2["inventory_cost_close"] == day2["inventory_cost_open"] + day2["inventory_cost_flow_kzt"]
    assert day2["capital_close"] == day2["cash_close"] + day2["receivables_close"] + day2["inventory_cost_close"]
