from scripts import update_cashflow_dashboard as dashboard


def _sample_rows() -> list[dict]:
    return [
        {
            "date": "2026-02-06",
            "cash_open": 40000000.0,
            "cash_close": 41000000.0,
            "receivables_open": 127000000.0,
            "receivables_close": 128000000.0,
            "inventory_cost_open": 26500000.0,
            "inventory_cost_close": 26600000.0,
            "inventory_on_hand_close": 18000000.0,
            "inventory_inbound_close": 7000000.0,
            "inventory_on_delivery_close": 1600000.0,
            "capital_close": 195600000.0,
            "is_forecast": False,
        },
        {
            "date": "2026-02-07",
            "cash_open": 41000000.0,
            "cash_close": 49363522.0,
            "receivables_open": 128000000.0,
            "receivables_close": 128237430.0,
            "inventory_cost_open": 26600000.0,
            "inventory_cost_close": 26658723.0,
            "inventory_on_hand_close": 18000000.0,
            "inventory_inbound_close": 6950000.0,
            "inventory_on_delivery_close": 1708723.0,
            "capital_close": 204259675.0,
            "is_forecast": False,
        },
    ]


def test_period_stats_use_paid_default_not_model_receivables() -> None:
    rows = _sample_rows()
    paid_truth = {
        "cash_actual_kzt": 2_003_917.0,
        "inventory_on_hand_paid_kzt": 20_127_636.0,
        "inventory_inbound_paid_kzt": 0.0,
        "inventory_on_delivery_paid_kzt": 0.0,
        "total_capital_paid_kzt": 22_131_554.0,
    }
    display_rows = dashboard.build_dashboard_rows_for_lens(
        rows,
        paid_truth=paid_truth,
        lens="paid_default",
    )

    assert display_rows[-1]["receivables_close"] == 0.0
    assert display_rows[-1]["cash_close"] == paid_truth["cash_actual_kzt"]
    assert display_rows[-1]["capital_close"] == paid_truth["total_capital_paid_kzt"]


def test_detailed_table_paid_default_does_not_show_legacy_model_receivables() -> None:
    rows = _sample_rows()
    display_rows = dashboard.build_dashboard_rows_for_lens(
        rows,
        paid_truth={"cash_actual_kzt": 1.0, "total_capital_paid_kzt": 2.0},
        lens="paid_default",
    )

    assert all(float(row.get("receivables_open", 0.0)) == 0.0 for row in display_rows)
    assert all(float(row.get("receivables_close", 0.0)) == 0.0 for row in display_rows)


def test_model_toggle_still_exposes_model_ledger_values() -> None:
    rows = _sample_rows()
    model_rows = dashboard.build_dashboard_rows_for_lens(
        rows,
        paid_truth={"cash_actual_kzt": 1.0, "total_capital_paid_kzt": 2.0},
        lens="model",
    )
    assert model_rows[-1]["receivables_close"] == 128237430.0
    assert model_rows[-1]["cash_close"] == 49363522.0
    assert model_rows[-1]["capital_close"] == 204259675.0
