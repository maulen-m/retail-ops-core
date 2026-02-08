from datetime import date

from scripts.rebuild_cashflow_calendar import compute_daily_rows


def test_rebuild_excludes_legacy_order_modelled_receivables_from_actual_rollforward() -> None:
    events = [
        {
            "event_date": "2026-02-07",
            "event_type": "SALE_ACCRUED",
            "account": "RECEIVABLES",
            "amount_kzt": 128237430.0,
            "source": "ORDER_MODELLED",
        },
        {
            "event_date": "2026-02-07",
            "event_type": "PAYOUT_RECEIVED",
            "account": "RECEIVABLES",
            "amount_kzt": 50000.0,
            "source": "STATEMENT_ACTUAL",
        },
    ]
    rows = compute_daily_rows(events, date(2026, 2, 7), date(2026, 2, 7), run_id="test")

    assert rows[0]["receivables_close"] == 50000.0


def test_rebuild_keeps_cash_and_inventory_rollforward_identities() -> None:
    events = [
        {
            "event_date": "2026-02-07",
            "event_type": "CASH_IN",
            "account": "KASPI_PAY_ACMEWEAR",
            "amount_kzt": 1000.0,
            "source": "STATEMENT_ACTUAL",
        },
        {
            "event_date": "2026-02-07",
            "event_type": "INVENTORY_MOVE",
            "account": "INVENTORY_ON_DELIVERY_COST",
            "amount_kzt": 300.0,
            "source": "ORDER_MODELLED",
        },
        {
            "event_date": "2026-02-07",
            "event_type": "SALE_ACCRUED",
            "account": "RECEIVABLES",
            "amount_kzt": 700.0,
            "source": "ORDER_MODELLED",
        },
    ]
    rows = compute_daily_rows(events, date(2026, 2, 7), date(2026, 2, 7), run_id="test")
    row = rows[0]

    assert row["cash_close"] == row["cash_open"] + row["cash_flow_kzt"]
    assert row["inventory_cost_close"] == row["inventory_cost_open"] + row["inventory_cost_flow_kzt"]
